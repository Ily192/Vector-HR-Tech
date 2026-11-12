"""La página de revisión de la cola (ADR-022): el GET solo muestra, el POST decide."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api import moderacion as api
from app.config import settings
from app.database import get_db
from app.domain.moderacion import EstadoDeModeracion, Gravedad, Marca, VacanteEnCola
from app.main import app
from app.security import enlaces_de_revision

from .test_moderar_vacantes import RepoFalso

SECRETO = "m" * 64


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> Iterator[RepoFalso]:
    falso = RepoFalso()
    monkeypatch.setattr(settings, "moderacion_secreto", SECRETO)
    monkeypatch.setattr(api, "SqlRepositorioDeModeracion", lambda _db: falso)

    async def sin_base() -> AsyncIterator[object]:
        yield object()

    app.dependency_overrides[get_db] = sin_base
    try:
        yield falso
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _en_cola(repo: RepoFalso, estado: EstadoDeModeracion) -> UUID:
    vid = uuid4()
    repo.cola.append(
        VacanteEnCola(
            id=vid,
            titulo="Promotor <b>urgente</b>",
            descripcion="Escríbenos por WhatsApp\n<script>alert(1)</script>",
            empresa="Andes & Cía",
            empresa_verificada=False,
            publica_para="clientes",
            estado=estado,
            motivos=(Marca("contacto_externo", "Manda a WhatsApp", Gravedad.MEDIA, cita="<x>"),),
        )
    )
    repo.estados[vid] = estado
    return vid


def test_el_get_muestra_la_vacante_escapada_y_no_cambia_nada(
    repo: RepoFalso, client: TestClient
) -> None:
    vid = _en_cola(repo, EstadoDeModeracion.EN_REVISION)
    token = enlaces_de_revision.firmar(SECRETO, vid)
    r = client.get("/moderacion/revisar", params={"t": token})
    assert r.status_code == 200
    assert "Promotor &lt;b&gt;urgente&lt;/b&gt;" in r.text
    assert "<script>" not in r.text
    assert "Reclutador(a) independiente" in r.text
    assert "Aprobar y publicar" in r.text
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert repo.estados[vid] is EstadoDeModeracion.EN_REVISION


def test_un_enlace_invalido_no_muestra_nada(repo: RepoFalso, client: TestClient) -> None:
    _en_cola(repo, EstadoDeModeracion.EN_REVISION)
    assert client.get("/moderacion/revisar", params={"t": "basura"}).status_code == 403
    assert client.get("/moderacion/revisar").status_code == 403


def test_aprobar_por_post(repo: RepoFalso, client: TestClient) -> None:
    vid = _en_cola(repo, EstadoDeModeracion.OCULTA)
    token = enlaces_de_revision.firmar(SECRETO, vid)
    r = client.post("/moderacion/revisar", data={"t": token, "accion": "aprobar"})
    assert r.status_code == 200
    assert "Aprobada" in r.text
    assert repo.estados[vid] is EstadoDeModeracion.PUBLICADA


def test_rechazar_por_post_con_motivo(repo: RepoFalso, client: TestClient) -> None:
    vid = _en_cola(repo, EstadoDeModeracion.EN_REVISION)
    token = enlaces_de_revision.firmar(SECRETO, vid)
    r = client.post(
        "/moderacion/revisar", data={"t": token, "accion": "rechazar", "motivo": "Pide depósito"}
    )
    assert r.status_code == 200
    assert repo.estados[vid] is EstadoDeModeracion.RECHAZADA
    marca = repo.motivos[vid]
    assert marca is not None and marca.corregir == "Pide depósito"


def test_rechazar_sin_motivo_pide_el_motivo(repo: RepoFalso, client: TestClient) -> None:
    vid = _en_cola(repo, EstadoDeModeracion.EN_REVISION)
    token = enlaces_de_revision.firmar(SECRETO, vid)
    r = client.post("/moderacion/revisar", data={"t": token, "accion": "rechazar", "motivo": " "})
    assert r.status_code == 422
    assert repo.estados[vid] is EstadoDeModeracion.EN_REVISION


def test_un_post_con_firma_falsa_no_decide(repo: RepoFalso, client: TestClient) -> None:
    vid = _en_cola(repo, EstadoDeModeracion.EN_REVISION)
    falso = enlaces_de_revision.firmar("otro" * 16, vid)
    r = client.post("/moderacion/revisar", data={"t": falso, "accion": "aprobar"})
    assert r.status_code == 403
    assert repo.estados[vid] is EstadoDeModeracion.EN_REVISION


def test_lo_ya_resuelto_responde_409(repo: RepoFalso, client: TestClient) -> None:
    vid = _en_cola(repo, EstadoDeModeracion.PUBLICADA)
    token = enlaces_de_revision.firmar(SECRETO, vid)
    r = client.post("/moderacion/revisar", data={"t": token, "accion": "aprobar"})
    assert r.status_code == 409
    assert "Publicada" in r.text


def test_accion_desconocida(repo: RepoFalso, client: TestClient) -> None:
    vid = _en_cola(repo, EstadoDeModeracion.EN_REVISION)
    token = enlaces_de_revision.firmar(SECRETO, vid)
    r = client.post("/moderacion/revisar", data={"t": token, "accion": "borrar"})
    assert r.status_code == 422


def test_sin_secreto_la_revision_no_esta_disponible(
    repo: RepoFalso, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "moderacion_secreto", "")
    assert client.get("/moderacion/revisar", params={"t": "x"}).status_code == 503
