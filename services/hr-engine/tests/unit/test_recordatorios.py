"""El recordatorio de postulados sin revisar (ADR-023): la regla, el correo y la tarea."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.application.recordar_postulados import RecordarPostuladosSinRevisar
from app.domain.recordatorios import (
    MAX_VACANTES_EN_EL_CORREO,
    PostuladosSinRevisar,
    VacanteConPostulados,
    armar_recordatorio,
    toca_recordar,
)
from app.infrastructure.recordatorios import _vacantes
from app.workers import recordatorios as worker
from app.workers.celery_app import celery_app

AHORA = datetime(2026, 11, 14, 15, 0, tzinfo=UTC)
PANEL = "https://panel.vectorhrtech.com"


def _empresa(**kw: object) -> PostuladosSinRevisar:
    datos: dict[str, object] = {
        "empresa_id": uuid4(),
        "empresa": "Andes Logística",
        "postulados": 6,
        "cruzo_el_umbral_en": AHORA - timedelta(hours=25),
        "recordado_en": None,
        "visto_en": None,
        "vacantes": (
            VacanteConPostulados("Coordinador de almacén", 4),
            VacanteConPostulados("Chofer repartidor", 2),
        ),
        "destinatarios": ("mariana@andes.mx",),
    }
    datos.update(kw)
    return PostuladosSinRevisar(**datos)  # type: ignore[arg-type]


# ─────────────────────────────── la regla ───────────────────────────────


def test_con_mas_de_5_y_24_horas_sin_entrar_toca() -> None:
    assert toca_recordar(_empresa(), AHORA)


def test_con_5_no_toca_aunque_pasen_dias() -> None:
    assert not toca_recordar(
        _empresa(postulados=5, cruzo_el_umbral_en=AHORA - timedelta(days=9)), AHORA
    )


def test_antes_de_24_horas_desde_el_sexto_no_toca() -> None:
    casi = _empresa(cruzo_el_umbral_en=AHORA - timedelta(hours=23, minutes=59))
    assert not toca_recordar(casi, AHORA)
    assert toca_recordar(replace(casi, cruzo_el_umbral_en=AHORA - timedelta(hours=24)), AHORA)


def test_no_se_repite_hasta_que_la_empresa_entre() -> None:
    recordada = _empresa(recordado_en=AHORA - timedelta(days=3), visto_en=None)
    assert not toca_recordar(recordada, AHORA)
    # Entró antes del recordatorio: sigue sin haber vuelto.
    assert not toca_recordar(replace(recordada, visto_en=AHORA - timedelta(days=4)), AHORA)
    # Entró después y se juntaron otros más de 5: vuelve a tocar.
    assert toca_recordar(replace(recordada, visto_en=AHORA - timedelta(days=2)), AHORA)


def test_el_umbral_y_la_espera_salen_de_la_config() -> None:
    e = _empresa(postulados=3, cruzo_el_umbral_en=AHORA - timedelta(hours=2))
    assert toca_recordar(e, AHORA, umbral=2, espera=timedelta(hours=1))


# ─────────────────────────────── el correo ───────────────────────────────


def test_el_correo_dice_cuantos_y_donde_sin_datos_de_candidatos() -> None:
    asunto, texto = armar_recordatorio(_empresa(), PANEL + "/")
    assert asunto == "Tienes 6 postulados sin revisar"
    assert "Andes Logística tiene 6 postulados que todavía no revisas" in texto
    assert "- Coordinador de almacén: 4 postulados" in texto
    assert "- Chofer repartidor: 2 postulados" in texto
    assert f"Entra a tu panel para verlos: {PANEL}\n" in texto
    assert "una sola vez" in texto
    assert "@" not in texto


def test_con_muchas_vacantes_nombra_las_primeras_y_cuenta_las_demas() -> None:
    vacantes = tuple(VacanteConPostulados(f"Puesto {i}", 1) for i in range(12))
    _, texto = armar_recordatorio(_empresa(postulados=12, vacantes=vacantes), PANEL)
    assert texto.count("- Puesto ") == MAX_VACANTES_EN_EL_CORREO
    assert "- Puesto 0: 1 postulado\n" in texto
    assert "- Y 2 vacantes más." in texto


def test_las_vacantes_de_la_base_se_leen_de_jsonb_o_de_texto() -> None:
    crudo = [{"titulo": "Analista", "postulados": 3}, "basura"]
    assert _vacantes(crudo) == (VacanteConPostulados("Analista", 3),)
    assert _vacantes('[{"titulo": "Analista", "postulados": 3}]') == _vacantes(crudo)
    assert _vacantes(None) == ()


# ─────────────────────────────── el caso de uso ───────────────────────────────


class RepositorioFalso:
    def __init__(self, empresas: Sequence[PostuladosSinRevisar], enviados: int = 0) -> None:
        self.empresas = list(empresas)
        self.enviados = enviados
        self.registrados: list[tuple[UUID, int, int]] = []
        self.pedido: tuple[int, int] | None = None

    async def con_postulados_sin_revisar(
        self, umbral: int, limite: int
    ) -> Sequence[PostuladosSinRevisar]:
        self.pedido = (umbral, limite)
        return self.empresas

    async def enviados_en_24_horas(self) -> int:
        return self.enviados

    async def registrar(self, empresa_id: UUID, *, postulados: int, destinatarios: int) -> None:
        self.registrados.append((empresa_id, postulados, destinatarios))


class CorreoFalso:
    def __init__(self, falla_para: frozenset[str] = frozenset()) -> None:
        self.enviados: list[tuple[str, str]] = []
        self.falla_para = falla_para

    async def enviar(self, *, para: str, asunto: str, texto: str) -> None:
        if para in self.falla_para:
            raise ConnectionRefusedError("smtp caído")
        self.enviados.append((para, asunto))


def _caso(
    repo: RepositorioFalso, correo: CorreoFalso, maximo: int = 20
) -> RecordarPostuladosSinRevisar:
    return RecordarPostuladosSinRevisar(
        repo, correo, panel_url=PANEL, max_en_24_horas=maximo, ahora=lambda: AHORA
    )


async def test_manda_un_correo_por_persona_y_lo_registra() -> None:
    empresa = _empresa(postulados=7, destinatarios=("mariana@andes.mx", "jose@andes.mx"))
    repo, correo = RepositorioFalso([empresa]), CorreoFalso()

    resultado = await _caso(repo, correo).ejecutar()

    assert [p for p, _ in correo.enviados] == ["mariana@andes.mx", "jose@andes.mx"]
    assert repo.registrados == [(empresa.empresa_id, 7, 2)]
    assert (resultado.empresas, resultado.correos) == (1, 2)
    assert repo.pedido == (5, 200)


async def test_a_quien_no_le_toca_no_le_llega_nada() -> None:
    repo = RepositorioFalso([_empresa(cruzo_el_umbral_en=AHORA - timedelta(hours=3))])
    correo = CorreoFalso()
    resultado = await _caso(repo, correo).ejecutar()
    assert correo.enviados == [] and repo.registrados == []
    assert resultado.empresas == 0


async def test_el_tope_diario_deja_cupo_a_los_codigos_de_acceso() -> None:
    primera, segunda = _empresa(), _empresa(destinatarios=("a@b.mx", "c@b.mx"))
    repo, correo = RepositorioFalso([primera, segunda], enviados=18), CorreoFalso()

    resultado = await _caso(repo, correo, maximo=20).ejecutar()

    # Quedaban 2: la primera usa 1 y a la segunda (2 personas) ya no le alcanza.
    assert [r[0] for r in repo.registrados] == [primera.empresa_id]
    assert (resultado.correos, resultado.sin_cupo) == (1, 1)


async def test_con_el_tope_agotado_no_sale_nada() -> None:
    repo, correo = RepositorioFalso([_empresa()], enviados=20), CorreoFalso()
    resultado = await _caso(repo, correo, maximo=20).ejecutar()
    assert correo.enviados == [] and resultado.sin_cupo == 1


async def test_sin_nadie_de_hr_con_correo_confirmado_no_se_registra() -> None:
    repo, correo = RepositorioFalso([_empresa(destinatarios=())]), CorreoFalso()
    resultado = await _caso(repo, correo).ejecutar()
    assert repo.registrados == [] and resultado.sin_destinatarios == 1


async def test_si_el_smtp_falla_con_todos_se_reintenta_la_hora_siguiente() -> None:
    repo = RepositorioFalso([_empresa()])
    resultado = await _caso(repo, CorreoFalso(frozenset({"mariana@andes.mx"}))).ejecutar()
    assert repo.registrados == []
    assert resultado.fallidos == ["ConnectionRefusedError"]


async def test_con_que_uno_lo_reciba_la_empresa_queda_avisada() -> None:
    empresa = _empresa(destinatarios=("mariana@andes.mx", "jose@andes.mx"))
    repo = RepositorioFalso([empresa])
    resultado = await _caso(repo, CorreoFalso(frozenset({"jose@andes.mx"}))).ejecutar()
    assert repo.registrados == [(empresa.empresa_id, 6, 1)]
    assert (resultado.correos, resultado.fallidos) == (1, ["ConnectionRefusedError"])


# ─────────────────────────────── la tarea ───────────────────────────────


def test_beat_lo_corre_cada_hora_y_la_tarea_existe() -> None:
    entrada = celery_app.conf.beat_schedule["postulados-recordar"]
    assert (entrada["task"], entrada["schedule"]) == ("postulados.recordar", 3600.0)
    assert entrada["options"]["expires"] < entrada["schedule"]
    celery_app.loader.import_default_modules()
    assert "postulados.recordar" in celery_app.tasks


def test_con_tope_cero_o_sin_smtp_no_corre(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_deberia_correr() -> dict[str, object]:
        raise AssertionError("no debería mandar nada")

    monkeypatch.setattr(worker, "_recordar", no_deberia_correr)
    monkeypatch.setattr(worker.settings, "recordatorio_max_24h", 0)
    assert worker.recordar() == {"apagado": True}
    monkeypatch.setattr(worker.settings, "recordatorio_max_24h", 20)
    monkeypatch.setattr(worker.settings, "smtp_host", "")
    assert worker.recordar() == {"sin_smtp": True}
