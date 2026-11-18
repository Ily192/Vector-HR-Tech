"""El área de admin del panel (`/admin`; ADR-022, enmienda del 2026-11-17).

Ilyra ve las métricas de la plataforma y aprueba o rechaza la cola de revisión desde el
panel, también instalado en el teléfono. Caddy publica `/admin/*` del hr-engine en
`api.`, con un tope de cuerpo chico. Es la misma cola que el resumen a hola@ con enlaces
firmados (`app/api/moderacion.py`) y la CLI: las tres usan `ResolverRevision`.

Auth: la sesión del panel (`Authorization: Bearer <access token de Supabase>`). El
hr-engine le pregunta a Auth de quién es (`GET /auth/v1/user`) y deja pasar solo a los
correos confirmados de `ADMIN_CORREOS`. No hay permisos nuevos en la base.

- `GET /admin/yo` → `{correo}`. Con 200, el panel muestra el enlace "Admin".
- `GET /admin/resumen` → los conteos del tablero.
- `GET /admin/cola` → la cola de revisión completa, con lo que hace falta para decidir.
- `POST /admin/vacantes/{id}/aprobar` y `POST /admin/vacantes/{id}/rechazar` (`{motivo}`,
  que la empresa ve en su panel) → 200; 409 si ya estaba decidida o no existe, con el
  estado en que está; 422 sin motivo.

Errores: 401 sin sesión o con una vencida; 403 si la cuenta no es de admin; 503 si Auth
no responde o el área no está configurada. Todo sale con `Cache-Control: no-store`
(middleware en `main.py`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, NoReturn
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.rate_limit import limiter
from app.application.moderar_vacantes import MotivoVacioError, ResolverRevision
from app.config import settings
from app.database import DbSession
from app.domain.admin import AuthNoDisponibleError, es_admin
from app.domain.moderacion import EstadoDeModeracion, VacanteEnCola
from app.infrastructure.admin import SesionesSupabase, SqlResumenDeLaPlataforma
from app.infrastructure.moderacion import SqlRepositorioDeModeracion
from app.monitoring import logger

router = APIRouter(prefix="/admin")

#: Lo que se espera a Auth antes de responder 503.
TIMEOUT_DE_AUTH_S = 5.0
#: El rechazo es un JSON con un motivo corto. Caddy corta antes, en 16 KB.
MAX_CUERPO = 16 * 1024
#: Un access token de Supabase ronda el kilobyte; uno de 8 KB no es de Auth.
MAX_TOKEN = 8 * 1024
ADMIN_RATE_LIMIT = settings.rate_limit_admin


# ─────────────────────────────── la sesión ───────────────────────────────


def _no_autorizado(detalle: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detalle, headers={"WWW-Authenticate": "Bearer"}
    )


async def exigir_admin(authorization: Annotated[str | None, Header()] = None) -> str:
    """El correo del admin de la sesión. Corre antes que el endpoint: sin ella, nada."""
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "el área de admin no está configurada"
        )
    esquema, _, token = (authorization or "").partition(" ")
    token = token.strip()
    if esquema.lower() != "bearer" or not token or len(token) > MAX_TOKEN:
        raise _no_autorizado("falta la sesión del panel")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_DE_AUTH_S) as http:
            sesiones = SesionesSupabase(settings.supabase_url, settings.supabase_secret_key, http)
            usuario = await sesiones.usuario(token)
    except AuthNoDisponibleError as exc:
        logger.warning("admin.auth_no_disponible", error=str(exc))
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "no se pudo revisar la sesión"
        ) from exc
    if usuario is None:
        raise _no_autorizado("la sesión venció o no es válida")
    if not es_admin(usuario, settings.correos_admin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "esta cuenta no es de admin")
    return usuario.correo


Admin = Annotated[str, Depends(exigir_admin)]


async def _cuerpo_chico(content_length: Annotated[int | None, Header()] = None) -> None:
    if content_length is not None and content_length > MAX_CUERPO:
        # 413 a secas: Starlette renombró la constante (HTTP_413_CONTENT_TOO_LARGE).
        raise HTTPException(413, "el cuerpo es muy largo")


# ─────────────────────────────── respuestas ───────────────────────────────


class Yo(BaseModel):
    correo: str


class EmpresasDelResumen(BaseModel):
    total: int
    #: Altas desde vectorhrtech.com/publicar-vacantes cuyo dueño escribió el código.
    altas_web_confirmadas: int
    verificadas: int


class VacantesDelResumen(BaseModel):
    #: Las abiertas, por estado de la moderación: pendiente, en_revision, publicada…
    por_moderacion: dict[EstadoDeModeracion, int]
    abiertas: int
    cerradas: int


class ConteoConSemana(BaseModel):
    total: int
    ultimos_7_dias: int


class AltasDelResumen(BaseModel):
    ultimos_7_dias: int


class Resumen(BaseModel):
    empresas: EmpresasDelResumen
    vacantes: VacantesDelResumen
    aplicaciones: ConteoConSemana
    altas: AltasDelResumen


class MotivoDeLaCola(BaseModel):
    regla: str
    senal: str
    gravedad: Literal["baja", "media", "alta"]
    cita: str | None
    corregir: str | None


class VacanteDeLaCola(BaseModel):
    id: UUID
    titulo: str
    empresa: str
    #: `clientes`: reclutador(a) independiente; nunca lleva la insignia.
    publica_para: str
    empresa_verificada: bool
    web: str | None
    linkedin: str | None
    estado: EstadoDeModeracion
    motivos: list[MotivoDeLaCola]
    descripcion: str
    creada_en: datetime | None


class Cola(BaseModel):
    vacantes: list[VacanteDeLaCola]


class Resuelta(BaseModel):
    estado: EstadoDeModeracion


class CuerpoDelRechazo(BaseModel):
    """`{motivo}`. Un campo de más es un 422. `ResolverRevision` lo recorta a 300."""

    model_config = ConfigDict(extra="forbid")

    motivo: Annotated[str, Field(max_length=2000)]


def _de_la_cola(v: VacanteEnCola) -> VacanteDeLaCola:
    return VacanteDeLaCola(
        id=v.id,
        titulo=v.titulo,
        empresa=v.empresa,
        publica_para=v.publica_para,
        empresa_verificada=v.empresa_verificada,
        web=v.web,
        linkedin=v.linkedin,
        estado=v.estado,
        # La misma forma que `vacantes.motivos_moderacion` (0019), la que lee el panel.
        motivos=[MotivoDeLaCola.model_validate(m.a_json()) for m in v.motivos],
        descripcion=v.descripcion,
        creada_en=v.creada_en,
    )


async def _sin_cambios(repositorio: SqlRepositorioDeModeracion, vacante_id: UUID) -> NoReturn:
    """409 como en `/moderacion/revisar`: ya estaba decidida, o ya no existe."""
    vacante = await repositorio.vacante_en_cola(vacante_id)
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        {
            "mensaje": "no se cambió nada",
            "estado": vacante.estado.value if vacante else None,
        },
    )


# ─────────────────────────────── endpoints ───────────────────────────────


@router.get("/yo", response_model=Yo)
@limiter.limit(ADMIN_RATE_LIMIT)
async def yo(request: Request, response: Response, correo: Admin) -> Yo:
    return Yo(correo=correo)


@router.get("/resumen", response_model=Resumen)
@limiter.limit(ADMIN_RATE_LIMIT)
async def resumen(request: Request, response: Response, _admin: Admin, db: DbSession) -> Resumen:
    r = await SqlResumenDeLaPlataforma(db).resumen()
    return Resumen(
        empresas=EmpresasDelResumen(
            total=r.empresas,
            altas_web_confirmadas=r.altas_web_confirmadas,
            verificadas=r.empresas_verificadas,
        ),
        vacantes=VacantesDelResumen(
            por_moderacion=dict(r.vacantes_por_moderacion),
            abiertas=r.vacantes_abiertas,
            cerradas=r.vacantes_cerradas,
        ),
        aplicaciones=ConteoConSemana(
            total=r.aplicaciones, ultimos_7_dias=r.aplicaciones_ultimos_7_dias
        ),
        altas=AltasDelResumen(ultimos_7_dias=r.altas_ultimos_7_dias),
    )


@router.get("/cola", response_model=Cola)
@limiter.limit(ADMIN_RATE_LIMIT)
async def cola(request: Request, response: Response, _admin: Admin, db: DbSession) -> Cola:
    vacantes = await SqlRepositorioDeModeracion(db).cola_completa()
    return Cola(vacantes=[_de_la_cola(v) for v in vacantes])


@router.post("/vacantes/{vacante_id}/aprobar", response_model=Resuelta)
@limiter.limit(ADMIN_RATE_LIMIT)
async def aprobar(
    request: Request, response: Response, vacante_id: UUID, correo: Admin, db: DbSession
) -> Resuelta:
    repositorio = SqlRepositorioDeModeracion(db)
    if not await ResolverRevision(repositorio).aprobar(vacante_id):
        await _sin_cambios(repositorio, vacante_id)
    logger.info("admin.aprobada", vacante_id=str(vacante_id), admin=correo)
    return Resuelta(estado=EstadoDeModeracion.PUBLICADA)


@router.post(
    "/vacantes/{vacante_id}/rechazar",
    response_model=Resuelta,
    dependencies=[Depends(_cuerpo_chico)],
)
@limiter.limit(ADMIN_RATE_LIMIT)
async def rechazar(
    request: Request,
    response: Response,
    vacante_id: UUID,
    cuerpo: CuerpoDelRechazo,
    correo: Admin,
    db: DbSession,
) -> Resuelta:
    repositorio = SqlRepositorioDeModeracion(db)
    try:
        hecho = await ResolverRevision(repositorio).rechazar(vacante_id, cuerpo.motivo)
    except MotivoVacioError as exc:
        # 422 a secas: el nombre de la constante cambió entre versiones de Starlette.
        raise HTTPException(422, "falta el motivo: la empresa lo ve en su panel") from exc
    if not hecho:
        await _sin_cambios(repositorio, vacante_id)
    logger.info("admin.rechazada", vacante_id=str(vacante_id), admin=correo)
    return Resuelta(estado=EstadoDeModeracion.RECHAZADA)
