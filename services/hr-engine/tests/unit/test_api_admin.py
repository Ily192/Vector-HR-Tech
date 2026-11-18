"""El área de admin del panel (ADR-022, enmienda del 2026-11-17): la sesión del panel, el
tablero y la cola de revisión. Auth y la base se reemplazan; el resto es la app real."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import admin as api
from app.api.rate_limit import limiter
from app.config import settings
from app.database import get_db
from app.domain.admin import AuthNoDisponibleError, ResumenDeLaPlataforma, UsuarioDeAuth
from app.domain.moderacion import EstadoDeModeracion, Gravedad, Marca, VacanteEnCola
from app.main import app

from .test_moderar_vacantes import RepoFalso

ADMIN = {"Authorization": "Bearer token-admin"}
CREADA = datetime(2026, 11, 16, 14, 30, tzinfo=UTC)


class SesionesFalsas:
    """Lo que Auth contesta por token: la cuenta, `None` (no sirve) o una excepción."""

    def __init__(self, usuarios: dict[str, UsuarioDeAuth | Exception | None]) -> None:
        self.usuarios = usuarios
        self.tokens: list[str] = []

    async def usuario(self, token: str) -> UsuarioDeAuth | None:
        self.tokens.append(token)
        respuesta = self.usuarios.get(token)
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


class ResumenFalso:
    async def resumen(self) -> ResumenDeLaPlataforma:
        return ResumenDeLaPlataforma(
            empresas=12,
            empresas_verificadas=4,
            altas_web_confirmadas=7,
            altas_ultimos_7_dias=3,
            vacantes_por_moderacion={
                EstadoDeModeracion.PENDIENTE: 1,
                EstadoDeModeracion.EN_REVISION: 2,
                EstadoDeModeracion.PUBLICADA: 9,
                EstadoDeModeracion.RECHAZADA: 1,
                EstadoDeModeracion.OCULTA: 0,
            },
            vacantes_abiertas=13,
            vacantes_cerradas=5,
            aplicaciones=80,
            aplicaciones_ultimos_7_dias=21,
        )


@dataclass
class Mundo:
    repo: RepoFalso
    sesiones: SesionesFalsas


@pytest.fixture
def mundo(monkeypatch: pytest.MonkeyPatch) -> Iterator[Mundo]:
    repo = RepoFalso()
    sesiones = SesionesFalsas(
        {
            # En otra capitalización que la de ADMIN_CORREOS: se compara sin mayúsculas.
            "token-admin": UsuarioDeAuth("Hola@VectorHRTech.com", confirmado=True),
            "token-sin-confirmar": UsuarioDeAuth("hola@vectorhrtech.com", confirmado=False),
            "token-empresa": UsuarioDeAuth("rh@andes.mx", confirmado=True),
            "token-caido": AuthNoDisponibleError("ConnectTimeout"),
        }
    )
    monkeypatch.setattr(settings, "supabase_url", "http://api-gw:8000")
    monkeypatch.setattr(settings, "supabase_secret_key", "sb_secret_de_prueba")
    monkeypatch.setattr(
        settings, "admin_correos", " hola@vectorhrtech.com, otra@vectorhrtech.com ,"
    )
    monkeypatch.setattr(api, "SesionesSupabase", lambda _url, _clave, _http: sesiones)
    monkeypatch.setattr(api, "SqlRepositorioDeModeracion", lambda _db: repo)
    monkeypatch.setattr(api, "SqlResumenDeLaPlataforma", lambda _db: ResumenFalso())
    # Cada test empieza con los topes en cero (el almacén es memoria).
    limiter.reset()

    async def sin_base() -> AsyncIterator[object]:
        yield object()

    app.dependency_overrides[get_db] = sin_base
    try:
        yield Mundo(repo=repo, sesiones=sesiones)
    finally:
        app.dependency_overrides.pop(get_db, None)
        limiter.reset()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _en_cola(mundo: Mundo, estado: EstadoDeModeracion = EstadoDeModeracion.EN_REVISION) -> UUID:
    vid = uuid4()
    mundo.repo.cola.append(
        VacanteEnCola(
            id=vid,
            titulo="Promotor de ventas",
            descripcion="Escríbenos por WhatsApp al 55 1234 5678.",
            empresa="Andes & Cía",
            empresa_verificada=False,
            publica_para="clientes",
            estado=estado,
            motivos=(
                Marca(
                    "contacto_externo",
                    "Manda a WhatsApp",
                    Gravedad.MEDIA,
                    cita="WhatsApp",
                    corregir="Deja que apliquen en la bolsa de empleo.",
                ),
            ),
            web="https://andes.mx",
            linkedin="https://www.linkedin.com/in/ana",
            creada_en=CREADA,
        )
    )
    mundo.repo.estados[vid] = estado
    return vid


# ─────────────────────────────── la sesión ───────────────────────────────


@pytest.mark.parametrize(
    "cabeceras",
    [{}, {"Authorization": "Basic token-admin"}, {"Authorization": "Bearer "}],
    ids=["sin-cabecera", "otro-esquema", "vacio"],
)
def test_sin_sesion_responde_401_sin_preguntarle_a_auth(
    mundo: Mundo, client: TestClient, cabeceras: dict[str, str]
) -> None:
    r = client.get("/admin/yo", headers=cabeceras)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    assert r.headers["cache-control"] == "no-store"
    assert mundo.sesiones.tokens == []


def test_una_sesion_vencida_o_falsa_responde_401(mundo: Mundo, client: TestClient) -> None:
    r = client.get("/admin/yo", headers={"Authorization": "Bearer token-vencido"})
    assert r.status_code == 401
    assert mundo.sesiones.tokens == ["token-vencido"]


def test_un_token_enorme_no_llega_a_auth(mundo: Mundo, client: TestClient) -> None:
    r = client.get("/admin/yo", headers={"Authorization": "Bearer " + "x" * (api.MAX_TOKEN + 1)})
    assert r.status_code == 401
    assert mundo.sesiones.tokens == []


@pytest.mark.parametrize("token", ["token-empresa", "token-sin-confirmar"])
def test_una_cuenta_que_no_es_de_admin_responde_403(
    mundo: Mundo, client: TestClient, token: str
) -> None:
    for ruta in ("/admin/yo", "/admin/resumen", "/admin/cola"):
        r = client.get(ruta, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403, ruta
        assert r.headers["cache-control"] == "no-store"


def test_el_admin_entra_y_auth_recibe_su_token(mundo: Mundo, client: TestClient) -> None:
    r = client.get("/admin/yo", headers=ADMIN)
    assert r.status_code == 200
    assert r.json() == {"correo": "Hola@VectorHRTech.com"}
    assert r.headers["cache-control"] == "no-store"
    assert mundo.sesiones.tokens == ["token-admin"]


def test_si_auth_no_responde_es_503(mundo: Mundo, client: TestClient) -> None:
    r = client.get("/admin/yo", headers={"Authorization": "Bearer token-caido"})
    assert r.status_code == 503


def test_sin_supabase_configurado_es_503(
    mundo: Mundo, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "supabase_secret_key", "")
    assert client.get("/admin/yo", headers=ADMIN).status_code == 503
    assert mundo.sesiones.tokens == []


def test_la_lista_de_admins_sale_del_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "admin_correos", " Hola@VectorHRTech.com ,, b@x.mx ")
    assert settings.correos_admin == frozenset({"hola@vectorhrtech.com", "b@x.mx"})


# ─────────────────────────────── el tablero y la cola ───────────────────────────────


def test_el_resumen(mundo: Mundo, client: TestClient) -> None:
    r = client.get("/admin/resumen", headers=ADMIN)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert r.json() == {
        "empresas": {"total": 12, "altas_web_confirmadas": 7, "verificadas": 4},
        "vacantes": {
            "por_moderacion": {
                "pendiente": 1,
                "en_revision": 2,
                "publicada": 9,
                "rechazada": 1,
                "oculta": 0,
            },
            "abiertas": 13,
            "cerradas": 5,
        },
        "aplicaciones": {"total": 80, "ultimos_7_dias": 21},
        "altas": {"ultimos_7_dias": 3},
    }


def test_la_cola_trae_lo_que_hace_falta_para_decidir(mundo: Mundo, client: TestClient) -> None:
    vid = _en_cola(mundo)
    _en_cola(mundo, EstadoDeModeracion.PUBLICADA)  # ya resuelta: no sale
    r = client.get("/admin/cola", headers=ADMIN)
    assert r.status_code == 200
    (vacante,) = r.json()["vacantes"]
    assert vacante == {
        "id": str(vid),
        "titulo": "Promotor de ventas",
        "empresa": "Andes & Cía",
        "publica_para": "clientes",
        "empresa_verificada": False,
        "web": "https://andes.mx",
        "linkedin": "https://www.linkedin.com/in/ana",
        "estado": "en_revision",
        "motivos": [
            {
                "regla": "contacto_externo",
                "senal": "Manda a WhatsApp",
                "gravedad": "media",
                "cita": "WhatsApp",
                "corregir": "Deja que apliquen en la bolsa de empleo.",
            }
        ],
        "descripcion": "Escríbenos por WhatsApp al 55 1234 5678.",
        "creada_en": "2026-11-16T14:30:00Z",
    }


# ─────────────────────────────── aprobar y rechazar ───────────────────────────────


def test_aprobar(mundo: Mundo, client: TestClient) -> None:
    vid = _en_cola(mundo, EstadoDeModeracion.OCULTA)
    r = client.post(f"/admin/vacantes/{vid}/aprobar", headers=ADMIN)
    assert r.status_code == 200
    assert r.json() == {"estado": "publicada"}
    assert r.headers["cache-control"] == "no-store"
    assert mundo.repo.estados[vid] is EstadoDeModeracion.PUBLICADA


def test_rechazar_con_motivo(mundo: Mundo, client: TestClient) -> None:
    vid = _en_cola(mundo)
    r = client.post(
        f"/admin/vacantes/{vid}/rechazar", headers=ADMIN, json={"motivo": "  Pide un depósito "}
    )
    assert r.status_code == 200
    assert r.json() == {"estado": "rechazada"}
    assert mundo.repo.estados[vid] is EstadoDeModeracion.RECHAZADA
    marca = mundo.repo.motivos[vid]
    assert marca is not None and marca.corregir == "Pide un depósito"


@pytest.mark.parametrize(
    "cuerpo",
    [{"motivo": "   "}, {}, {"motivo": "Pide un depósito", "extra": 1}],
    ids=["en-blanco", "sin-motivo", "campo-de-mas"],
)
def test_rechazar_sin_motivo_es_422_y_no_cambia_nada(
    mundo: Mundo, client: TestClient, cuerpo: dict[str, object]
) -> None:
    vid = _en_cola(mundo)
    r = client.post(f"/admin/vacantes/{vid}/rechazar", headers=ADMIN, json=cuerpo)
    assert r.status_code == 422
    assert mundo.repo.estados[vid] is EstadoDeModeracion.EN_REVISION


def test_un_cuerpo_grande_es_413(mundo: Mundo, client: TestClient) -> None:
    vid = _en_cola(mundo)
    r = client.post(
        f"/admin/vacantes/{vid}/rechazar",
        headers=ADMIN,
        json={"motivo": "x" * (api.MAX_CUERPO + 1)},
    )
    assert r.status_code == 413
    assert mundo.repo.estados[vid] is EstadoDeModeracion.EN_REVISION


def test_lo_ya_resuelto_responde_409_con_su_estado(mundo: Mundo, client: TestClient) -> None:
    vid = _en_cola(mundo, EstadoDeModeracion.PUBLICADA)
    r = client.post(f"/admin/vacantes/{vid}/aprobar", headers=ADMIN)
    assert r.status_code == 409
    assert r.json()["detail"] == {"mensaje": "no se cambió nada", "estado": "publicada"}

    rechazada = _en_cola(mundo, EstadoDeModeracion.RECHAZADA)
    r = client.post(f"/admin/vacantes/{rechazada}/rechazar", headers=ADMIN, json={"motivo": "x"})
    assert r.status_code == 409
    assert r.json()["detail"]["estado"] == "rechazada"


def test_una_vacante_que_ya_no_existe_responde_409(mundo: Mundo, client: TestClient) -> None:
    r = client.post(f"/admin/vacantes/{uuid4()}/aprobar", headers=ADMIN)
    assert r.status_code == 409
    assert r.json()["detail"]["estado"] is None


def test_sin_ser_admin_no_decide(mundo: Mundo, client: TestClient) -> None:
    vid = _en_cola(mundo)
    empresa = {"Authorization": "Bearer token-empresa"}
    assert client.post(f"/admin/vacantes/{vid}/aprobar", headers=empresa).status_code == 403
    r = client.post(f"/admin/vacantes/{vid}/rechazar", headers=empresa, json={"motivo": "x"})
    assert r.status_code == 403
    assert client.post(f"/admin/vacantes/{vid}/aprobar").status_code == 401
    assert mundo.repo.estados[vid] is EstadoDeModeracion.EN_REVISION


def test_un_id_que_no_es_uuid_es_422(mundo: Mundo, client: TestClient) -> None:
    assert client.post("/admin/vacantes/123/aprobar", headers=ADMIN).status_code == 422


def test_el_tope_por_ip(mundo: Mundo, client: TestClient) -> None:
    tope = int(settings.rate_limit_admin.split("/")[0])
    estados = [client.get("/admin/yo", headers=ADMIN).status_code for _ in range(tope + 1)]
    assert estados[:tope] == [200] * tope
    assert estados[tope] == 429
