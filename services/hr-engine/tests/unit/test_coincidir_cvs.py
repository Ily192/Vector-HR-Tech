"""Caso de uso CoincidirCvsPendientes con adaptadores falsos: sin base, sin red y sin IA (ADR-019)."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.application.coincidir_cvs import CoincidirCvsPendientes, ResultadoDelBarrido
from app.domain.entidades import CvPendiente
from tests.unit.fakes import (
    AlmacenEnMemoria,
    ExtractorDeTextoPlano,
    RepositorioDeCoincidenciasEnMemoria,
)

EMPRESA_ID = UUID("00000000-0000-0000-0000-000000000001")
SKILLS = ("Python", "SQL", "Docker")
#: Relleno para que el CV tenga letras de sobra (`MIN_LETRAS_LEGIBLES`).
RELLENO = " Analista con experiencia en proyectos de datos para clientes de la región." * 3


def _cv(skills: tuple[str, ...] = SKILLS) -> CvPendiente:
    application_id = uuid4()
    return CvPendiente(
        application_id=application_id,
        empresa_id=EMPRESA_ID,
        ruta=f"{EMPRESA_ID}/{application_id}.pdf",
        skills=skills,
    )


def _caso(
    pendientes: list[CvPendiente], cvs: dict[str, bytes], **almacen: bool
) -> tuple[CoincidirCvsPendientes, RepositorioDeCoincidenciasEnMemoria, AlmacenEnMemoria]:
    repo = RepositorioDeCoincidenciasEnMemoria(pendientes_=pendientes)
    storage = AlmacenEnMemoria(cvs=cvs, **almacen)
    return CoincidirCvsPendientes(repo, storage, ExtractorDeTextoPlano()), repo, storage


async def test_guarda_las_skills_que_menciona_cada_cv() -> None:
    uno, otro = _cv(), _cv()
    caso, repo, _ = _caso(
        [uno, otro],
        {
            uno.ruta: f"Python y SQL.{RELLENO}".encode(),
            otro.ruta: f"Docker, Python y SQL.{RELLENO}".encode(),
        },
    )
    assert await caso.ejecutar(lote=10) == ResultadoDelBarrido(revisados=2)
    assert repo.guardadas == {
        uno.application_id: ("Python", "SQL"),
        otro.application_id: ("Python", "SQL", "Docker"),
    }
    assert repo.ilegibles == set()


async def test_el_cv_que_no_esta_en_storage_queda_ilegible() -> None:
    cv = _cv()
    caso, repo, _ = _caso([cv], {})
    assert await caso.ejecutar(lote=10) == ResultadoDelBarrido(ilegibles=1)
    assert repo.ilegibles == {cv.application_id}


@pytest.mark.parametrize(
    "contenido",
    [b"\x00formato que no se lee", b"Python SQL", b""],
    ids=["formato-no-legible", "escaneado-casi-sin-texto", "vacio"],
)
async def test_lo_que_no_se_puede_leer_queda_ilegible(contenido: bytes) -> None:
    cv = _cv()
    caso, repo, _ = _caso([cv], {cv.ruta: contenido})
    assert await caso.ejecutar(lote=10) == ResultadoDelBarrido(ilegibles=1)
    assert repo.ilegibles == {cv.application_id}
    assert repo.guardadas == {}


async def test_si_storage_no_responde_el_resto_del_lote_espera() -> None:
    pendientes = [_cv() for _ in range(3)]
    caso, repo, storage = _caso(pendientes, {}, caido=True)
    assert await caso.ejecutar(lote=10) == ResultadoDelBarrido(en_espera=3)
    # No insiste con los demás: si Storage no responde, no va a responder al siguiente.
    assert storage.descargas == [pendientes[0].ruta]
    # El que se intentó no queda ilegible: se reintenta en el siguiente barrido.
    assert repo.ilegibles == set()


async def test_si_la_empresa_cambio_las_skills_no_se_guarda() -> None:
    cv = _cv()
    caso, repo, _ = _caso([cv], {cv.ruta: f"Python.{RELLENO}".encode()})
    repo.skills_de_hoy[cv.application_id] = ("Python", "Kotlin")
    assert await caso.ejecutar(lote=10) == ResultadoDelBarrido(descartados=1)
    assert repo.guardadas == {}
    assert repo.ilegibles == set()  # el siguiente barrido lo recalcula


async def test_marca_el_cv_antes_de_leerlo() -> None:
    """Si leer un PDF malicioso tumba el proceso, ese CV no vuelve a bloquear el barrido."""
    cv = _cv()

    class ExtractorQueRevienta:
        def extraer(self, contenido: bytes) -> str | None:
            raise MemoryError("PDF malicioso")

    repo = RepositorioDeCoincidenciasEnMemoria(pendientes_=[cv])
    caso = CoincidirCvsPendientes(
        repo, AlmacenEnMemoria(cvs={cv.ruta: b"%PDF"}), ExtractorQueRevienta()
    )
    with pytest.raises(MemoryError):
        await caso.ejecutar(lote=10)
    assert repo.eventos == [("marcar", cv.application_id)]
    assert repo.ilegibles == {cv.application_id}


async def test_el_lote_limita_cuantos_cvs_se_revisan() -> None:
    pendientes = [_cv() for _ in range(5)]
    cvs = {cv.ruta: f"Python.{RELLENO}".encode() for cv in pendientes}
    caso, repo, _ = _caso(pendientes, cvs)
    assert (await caso.ejecutar(lote=2)).revisados == 2
    assert len(repo.guardadas) == 2
