"""Puertos de la evaluación, de la coincidencia de skills y del alta de empresas: lo que el
dominio necesita del mundo exterior.

Los implementan los adaptadores de infraestructura (SQL, OpenAI, Gemini) y, en
los tests, adaptadores falsos. El dominio solo conoce estas firmas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from app.domain.alta import SolicitudDeAlta
from app.domain.alta_web import SolicitudDeAltaWeb
from app.domain.anonimizacion import CvAnonimo
from app.domain.entidades import (
    AplicacionPorEvaluar,
    Candidato,
    CvPendiente,
    Embedding,
    FitScore,
    PerfilAnonimo,
    ResultadoScoring,
    Vacante,
)


class ProveedorNoDisponibleError(RuntimeError):
    """El proveedor no puede atender ahora: caído, sin configurar, con timeouts,
    con 429/5xx o con el circuito abierto.

    Los adaptadores traducen a esta excepción los errores de disponibilidad de su
    SDK. Los demás fallos (una respuesta inválida, un 400) no se traducen: son
    errores de verdad y tienen que verse.
    """


class CandidateRepository(Protocol):
    """Lectura y escritura de candidatos, vacantes y applications de un tenant.

    Ve solo lo que deja ver el tenant de la sesión: un id de otra empresa se
    comporta como inexistente (`None`).
    """

    async def get_vacante(self, vacante_id: UUID) -> Vacante | None: ...

    async def get_candidato(self, candidato_id: UUID) -> Candidato | None: ...

    async def update_vacante_embedding(
        self, vacante_id: UUID, vector: tuple[float, ...]
    ) -> None: ...

    async def update_candidato_embedding(
        self, candidato_id: UUID, vector: tuple[float, ...]
    ) -> None: ...

    async def upsert_application(
        self,
        *,
        empresa_id: UUID,
        vacante_id: UUID,
        candidato_id: UUID,
        fit: FitScore,
    ) -> UUID:
        """Crea o actualiza la application (vacante, candidato) y devuelve su id."""
        ...


class EmbeddingProvider(Protocol):
    """Genera el embedding de un texto.

    Si el proveedor no está disponible lanza `ProveedorNoDisponibleError`. Los
    embeddings sirven a la búsqueda del sourcer, así que la evaluación sigue sin él.
    """

    async def embed(self, texto: str) -> Embedding: ...


class ScoringProvider(Protocol):
    """Puntúa el encaje de un perfil con un ICP.

    Recibe un `PerfilAnonimo` y no un `Candidato`: así el tipo impide que el
    nombre llegue al modelo. Si ningún modelo está disponible lanza
    `ProveedorNoDisponibleError`, y quien llama aplaza la evaluación.
    """

    async def score(self, perfil: PerfilAnonimo, icp: str) -> ResultadoScoring: ...


# ─── Coincidencia de skills del plan gratis (ADR-019) ────────────────────────


class CvInaccesibleError(LookupError):
    """El CV no se puede bajar y no se podrá después: no existe o pasa del tamaño máximo."""


class AlmacenNoDisponibleError(RuntimeError):
    """Storage no responde o rechaza la clave. El CV espera al siguiente barrido."""


class AlmacenDeCvs(Protocol):
    """Los CVs que subieron los candidatos. Solo existe del lado del servidor."""

    async def descargar(self, ruta: str) -> bytes: ...


class ExtractorDeTexto(Protocol):
    def extraer(self, contenido: bytes) -> str | None:
        """El texto del CV, o None si su formato no se puede leer (.doc, imagen, dañado)."""
        ...


class RepositorioDeCoincidencias(Protocol):
    """Las coincidencias y los CVs ilegibles, en el esquema `privado`."""

    async def pendientes(self, limite: int) -> list[CvPendiente]: ...

    async def guardar(self, cv: CvPendiente, encontradas: tuple[str, ...]) -> bool:
        """Guarda la coincidencia solo si la vacante sigue pidiendo `cv.skills`.

        Devuelve si la guardó. Al guardarla, el CV deja de estar marcado como ilegible.
        """
        ...

    async def marcar_ilegible(self, cv: CvPendiente) -> None: ...

    async def desmarcar_ilegible(self, cv: CvPendiente) -> None: ...


# ─── Evaluación con IA del plan de pago (ADR-021) ────────────────────────────


class EvaluadorDeCvs(Protocol):
    """Puntúa el CV de un candidato contra el perfil de la vacante.

    Recibe un `CvAnonimo`, que solo crea `anonimizar`: así el tipo impide que el
    CV llegue al modelo con el nombre o el contacto. Si ningún modelo está
    disponible lanza `ProveedorNoDisponibleError` y la aplicación espera.
    """

    async def evaluar(self, cv: CvAnonimo, vacante: str) -> ResultadoScoring: ...


class RepositorioDeEvaluaciones(Protocol):
    """Las evaluaciones del plan de pago y su cuenta, en `privado.evaluaciones_ia`."""

    async def gastado_este_mes(self) -> float:
        """Lo que costaron este mes las evaluaciones de cv-evaluator, de todas las empresas."""
        ...

    async def reclamar(self, limite: int) -> list[AplicacionPorEvaluar]:
        """Toma hasta `limite` aplicaciones pendientes de empresas con IA bajo su tope.

        Cada una suma un intento al reclamarla, y ningún otro barrido la toma mientras.
        """
        ...

    async def guardar(self, aplicacion: AplicacionPorEvaluar, resultado: ResultadoScoring) -> bool:
        """Guarda la evaluación y la pasa a "Evaluados".

        No la guarda si entretanto el candidato se opuso o la empresa dejó el plan con
        IA, y devuelve si la guardó. El costo se registra igual: ya se gastó.
        """
        ...

    async def aplazar(self, aplicacion: AplicacionPorEvaluar, *, motivo: str) -> None:
        """La deja para el siguiente barrido. Con `MAX_INTENTOS` queda sin evaluar."""
        ...

    async def soltar(self, aplicacion: AplicacionPorEvaluar) -> None:
        """La devuelve sin gastar su intento: lo que falló fue Storage, no el CV."""
        ...

    async def marcar_ilegible(self, aplicacion: AplicacionPorEvaluar) -> None: ...


# ─── Alta de empresas (plan gratis) ──────────────────────────────────────────

#: Qué hay en Auth para un correo: nada, una invitación sin aceptar o una cuenta en uso.
EstadoDeCuenta = Literal["sin-cuenta", "pendiente", "confirmada"]


class CuentaYaExisteError(RuntimeError):
    """El correo ya tiene cuenta en Auth: no se le puede dar de alta otra vez."""


class InvitacionNoEnviadaError(RuntimeError):
    """Auth no mandó la invitación: caído, sin clave válida o con el límite de correos."""


class RepositorioDeAltas(Protocol):
    """Las empresas, sus invitaciones y las cuentas de Auth, con el rol dueño de la base."""

    async def estado_de_la_cuenta(self, correo: str) -> EstadoDeCuenta: ...

    async def crear_empresa_con_invitacion(
        self, solicitud: SolicitudDeAlta, slug: str, token_hash: str
    ) -> UUID | None:
        """Crea la empresa con plan gratis y su invitación, juntas y confirmadas.

        Devuelve el id de la empresa, o None si el slug ya es de otra.
        """
        ...

    async def deshacer(self, empresa_id: UUID) -> None:
        """Borra la empresa recién creada; su invitación se va en cascada."""
        ...


class ServicioDeInvitaciones(Protocol):
    """El correo de invitación de Supabase Auth. Solo del lado del servidor."""

    async def invitar(self, correo: str, token: str, nombre: str) -> None:
        """Crea la cuenta y manda el correo. `handle_new_user` (0003) la liga a su empresa
        con el token. Lanza `CuentaYaExisteError` o `InvitacionNoEnviadaError`."""
        ...

    async def reenviar(self, correo: str) -> None:
        """Vuelve a mandar el correo a una cuenta que todavía no entra."""
        ...


# ─── Alta desde la web, con código ──────────────────────────────────────────

#: Qué pasó con un registro de la web: se creó la empresa o el correo ya tenía cuenta.
ResultadoDeAltaWeb = Literal["empresa_creada", "cuenta_existente"]


class CodigoNoEnviadoError(RuntimeError):
    """Auth no mandó el código: caído, sin clave válida o con su límite de correos."""


class CodigoReenviadoMuyProntoError(RuntimeError):
    """Ya hay un código de hace menos de un minuto (GOTRUE_SMTP_MAX_FREQUENCY): sigue
    sirviendo, así que no es un error para quien se registra."""


class LimiteDeAltasError(RuntimeError):
    """Demasiados registros de la misma IP o del mismo correo en la última hora."""

    def __init__(self, reintentar_en_s: int) -> None:
        super().__init__(f"límite de altas: reintentar en {reintentar_en_s} s")
        self.reintentar_en_s = reintentar_en_s


@dataclass(frozen=True)
class AltaPendiente:
    """Una empresa que se registró por la web y nunca escribió su código."""

    empresa_id: UUID
    usuarios: tuple[UUID, ...]


class RepositorioDeAltasWeb(Protocol):
    """Los registros de la web (`altas_web`): idempotencia, datos para verificar y limpieza."""

    async def reservar(self, solicitud: SolicitudDeAltaWeb, ip_hash: str | None) -> bool:
        """Guarda el `lead_id`. False si ya estaba: es un reintento de la web."""
        ...

    async def completar(
        self, lead_id: str, empresa_id: UUID | None, resultado: ResultadoDeAltaWeb
    ) -> None: ...

    async def liberar(self, lead_id: str) -> None:
        """Quita la reserva si el alta falló, para que la web pueda reintentar."""
        ...

    async def marcar_confirmadas(self) -> int:
        """Pone `confirmado_en` a las altas cuyo dueño ya escribió el código."""
        ...

    async def pendientes_desde(self, antes_de: datetime) -> list[AltaPendiente]:
        """Las empresas creadas por la web antes de `antes_de` en las que nadie confirmó
        su correo, sin vacantes. Nunca devuelve una empresa con una cuenta confirmada."""
        ...

    async def borrar_empresa(self, empresa_id: UUID) -> None:
        """Borra la empresa; su invitación y su alta se van en cascada."""
        ...


class ServicioDeCodigos(Protocol):
    """El correo con el código de 6 dígitos de Supabase Auth (`POST /auth/v1/otp`)."""

    async def mandar_codigo_de_alta(
        self, correo: str, token: str, nombre: str, ip: str | None
    ) -> None:
        """Crea la cuenta con el token de la invitación en el metadata, que es lo que
        `handle_new_user` (0003) busca, y le manda el código. Lanza
        `CodigoNoEnviadoError` o `CodigoReenviadoMuyProntoError`."""
        ...

    async def mandar_codigo_de_entrada(self, correo: str, ip: str | None) -> None:
        """Manda un código a una cuenta que ya existe, sin crear nada."""
        ...

    async def borrar_usuario(self, usuario_id: UUID) -> None:
        """Borra la cuenta de Auth (API de administración)."""
        ...


class LimitadorDeAltas(Protocol):
    """Topes de registros por hash de IP y por correo."""

    async def consumir(self, ip_hash: str | None, correo: str) -> None:
        """Cuenta un intento. Lanza `LimiteDeAltasError` si alguno se pasó."""
        ...
