"""Caso de uso de la evaluación con IA del plan de pago, con adaptadores falsos (ADR-021)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.evaluar_aplicaciones import EvaluarAplicacionesPendientes
from app.domain.anonimizacion import NOMBRE
from app.domain.entidades import AplicacionPorEvaluar, FitScore, VacanteParaEvaluar
from app.domain.puertos import ProveedorNoDisponibleError
from tests.unit.fakes import (
    AlmacenEnMemoria,
    EvaluadorFalso,
    ExtractorDeTextoPlano,
    RepositorioDeEvaluacionesEnMemoria,
)

VACANTE = VacanteParaEvaluar(
    titulo="Analista de inventarios",
    descripcion="Controlarás el inventario del almacén.",
    skills=("Excel", "Inventarios"),
    nivel="mid",
    modalidad="onsite",
    ubicacion="Monterrey, NL",
    icp_text=None,
)
FIT = FitScore(score=7.5, rationale="Buen encaje con el control de inventarios.")
RELLENO = (
    "Experiencia coordinando equipos de trabajo en centros de distribución, con enfoque "
    "en seguridad, orden y cumplimiento de metas diarias del turno."
)


def _aplicacion(nombre: str, *, plan: str = "ia") -> AplicacionPorEvaluar:
    return AplicacionPorEvaluar(
        application_id=uuid4(),
        empresa_id=uuid4(),
        plan=plan,
        ruta=f"empresa/{uuid4()}.pdf",
        nombre=nombre,
        correo=f"{nombre.split()[0].lower()}@correo.test",
        vacante=VACANTE,
    )


def _cv(aplicacion: AplicacionPorEvaluar, texto: str = RELLENO) -> bytes:
    return f"{aplicacion.nombre}\n{aplicacion.correo}\n{texto}".encode()


def _caso(
    pendientes: list[AplicacionPorEvaluar],
    cvs: dict[str, bytes],
    *,
    evaluador: EvaluadorFalso | None = None,
    almacen: AlmacenEnMemoria | None = None,
    gastado: float = 0.0,
    en_paralelo: int = 4,
) -> tuple[EvaluarAplicacionesPendientes, RepositorioDeEvaluacionesEnMemoria, EvaluadorFalso]:
    repositorio = RepositorioDeEvaluacionesEnMemoria(pendientes_=pendientes, gastado=gastado)
    evaluador = evaluador or EvaluadorFalso(fit=FIT)
    caso = EvaluarAplicacionesPendientes(
        repositorio,
        almacen or AlmacenEnMemoria(cvs=cvs),
        ExtractorDeTextoPlano(),
        evaluador,
        presupuesto_mensual_usd=25.0,
        en_paralelo=en_paralelo,
    )
    return caso, repositorio, evaluador


async def test_evalua_cada_cv_a_ciegas_contra_el_perfil_de_la_vacante() -> None:
    ana, jose = _aplicacion("Ana Paz"), _aplicacion("José Ruiz")
    caso, repositorio, evaluador = _caso([ana, jose], {a.ruta: _cv(a) for a in (ana, jose)})

    resultado = await caso.ejecutar(lote=10)

    assert (resultado.evaluadas, resultado.ilegibles, resultado.aplazadas) == (2, 0, 0)
    assert resultado.costo_usd == pytest.approx(2 * evaluador.costo_usd)
    assert set(repositorio.guardadas) == {ana.application_id, jose.application_id}
    for (cv, vacante), aplicacion in zip(evaluador.recibido, (ana, jose), strict=True):
        assert aplicacion.nombre.split()[0] not in cv.texto
        assert str(aplicacion.correo) not in cv.texto
        assert cv.texto.startswith(NOMBRE)
        assert vacante == VACANTE.perfil()


async def test_el_perfil_de_la_vacante_lleva_lo_que_pide_y_no_a_la_empresa() -> None:
    perfil = VACANTE.perfil()
    for dato in ("Analista de inventarios", "Excel, Inventarios", "Monterrey, NL", "mid"):
        assert dato in perfil
    assert "Perfil ideal" not in perfil


async def test_con_el_presupuesto_del_mes_agotado_no_reclama_nada() -> None:
    ana = _aplicacion("Ana Paz")
    caso, repositorio, evaluador = _caso([ana], {ana.ruta: _cv(ana)}, gastado=25.0)

    resultado = await caso.ejecutar(lote=10)

    assert resultado.en_pausa
    assert repositorio.reclamos == 0
    assert evaluador.recibido == []


async def test_lo_ilegible_se_marca_y_no_llega_al_modelo() -> None:
    corto, doc, perdido, bueno = (
        _aplicacion(n) for n in ("Ana Paz", "Luis Mar", "Eva Sol", "Ivo Lee")
    )
    cvs = {
        corto.ruta: _cv(corto, "Python."),  # menos de 100 letras
        doc.ruta: b"\x00un .doc",
        bueno.ruta: _cv(bueno),
    }
    caso, repositorio, evaluador = _caso([corto, doc, perdido, bueno], cvs)

    resultado = await caso.ejecutar(lote=10)

    assert resultado.ilegibles == 3
    assert repositorio.ilegibles == {
        corto.application_id,
        doc.application_id,
        perdido.application_id,
    }
    assert len(evaluador.recibido) == 1
    assert set(repositorio.guardadas) == {bueno.application_id}


async def test_si_storage_no_responde_suelta_el_resto_sin_gastar_intentos() -> None:
    ana, jose = _aplicacion("Ana Paz"), _aplicacion("José Ruiz")
    caso, repositorio, evaluador = _caso([ana, jose], {}, almacen=AlmacenEnMemoria(caido=True))

    resultado = await caso.ejecutar(lote=10)

    assert resultado.aplazadas == 2
    assert repositorio.sueltas == {ana.application_id, jose.application_id}
    assert evaluador.recibido == []


async def test_si_el_modelo_no_esta_disponible_espera_sin_gastar_su_intento() -> None:
    """Una caída de Gemini no es culpa del CV: no puede dejarlo "sin evaluar"."""
    ana, jose = _aplicacion("Ana Paz"), _aplicacion("José Ruiz")
    evaluador = EvaluadorFalso(
        fit=FIT, errores={"falla aquí": ProveedorNoDisponibleError("Gemini caído")}
    )
    caso, repositorio, _ = _caso(
        [ana, jose],
        {ana.ruta: _cv(ana, f"{RELLENO} falla aquí"), jose.ruta: _cv(jose)},
        evaluador=evaluador,
    )

    resultado = await caso.ejecutar(lote=10)

    assert (resultado.evaluadas, resultado.aplazadas, resultado.sin_modelo) == (1, 1, 1)
    assert repositorio.sueltas == {ana.application_id}
    assert repositorio.aplazadas == {}
    assert set(repositorio.guardadas) == {jose.application_id}


async def test_una_respuesta_invalida_tambien_se_aplaza_sin_tumbar_el_lote() -> None:
    ana = _aplicacion("Ana Paz")
    evaluador = EvaluadorFalso(fit=FIT, errores={"distribución": ValueError("JSON inválido")})
    caso, repositorio, _ = _caso([ana], {ana.ruta: _cv(ana)}, evaluador=evaluador)

    resultado = await caso.ejecutar(lote=10)

    assert resultado.aplazadas == 1
    assert repositorio.aplazadas == {ana.application_id: "ValueError"}


async def test_si_el_candidato_se_opuso_mientras_tanto_no_cuenta_como_evaluada() -> None:
    ana = _aplicacion("Ana Paz")
    caso, repositorio, evaluador = _caso([ana], {ana.ruta: _cv(ana)})
    repositorio.opuestas.add(ana.application_id)

    resultado = await caso.ejecutar(lote=10)

    assert resultado.evaluadas == 0
    # El modelo ya cobró: el costo se registra igual.
    assert resultado.costo_usd == pytest.approx(evaluador.costo_usd)


async def test_una_empresa_que_dejo_el_plan_con_ia_no_se_evalua() -> None:
    gratis = _aplicacion("Ana Paz", plan="gratis")
    caso, repositorio, evaluador = _caso([gratis], {gratis.ruta: _cv(gratis)})

    await caso.ejecutar(lote=10)

    assert repositorio.sueltas == {gratis.application_id}
    assert evaluador.recibido == []


async def test_puntua_en_paralelo_sin_pasar_del_limite() -> None:
    aplicaciones = [_aplicacion(f"Persona Numero{i}") for i in range(9)]
    caso, repositorio, evaluador = _caso(
        aplicaciones, {a.ruta: _cv(a) for a in aplicaciones}, en_paralelo=3
    )

    resultado = await caso.ejecutar(lote=10)

    assert resultado.evaluadas == 9
    assert evaluador.en_curso_max == 3
    # Las escrituras van en orden: una sesión de base no se usa a la vez.
    assert [e for e, _ in repositorio.eventos] == ["guardar"] * 9


async def test_el_lote_limita_cuantas_reclama() -> None:
    aplicaciones = [_aplicacion(f"Persona Numero{i}") for i in range(5)]
    caso, repositorio, _ = _caso(aplicaciones, {a.ruta: _cv(a) for a in aplicaciones})

    resultado = await caso.ejecutar(lote=2)

    assert resultado.evaluadas == 2
    assert len(repositorio.guardadas) == 2
