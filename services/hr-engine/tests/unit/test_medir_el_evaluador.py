"""Medir al evaluador de CVs con un evaluador falso que puntúa según el texto (ADR-021 §9)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from app.application.medir_el_evaluador import MedirElEvaluador
from app.domain.anonimizacion import CvAnonimo
from app.domain.entidades import FitScore, ResultadoScoring, VacanteParaEvaluar
from app.domain.evals import EJES, CasoDeEval
from app.domain.puertos import ProveedorNoDisponibleError

VACANTE = VacanteParaEvaluar(
    titulo="Analista de datos",
    descripcion="Tableros en Power BI y consultas en SQL.",
    skills=("SQL", "Power BI"),
    nivel="semi-senior",
    modalidad="hybrid",
    ubicacion="Monterrey, NL",
    icp_text=None,
)


def _caso(id_: str, score: float, esperado: float | None = None) -> CasoDeEval:
    """El evaluador falso lee el score del propio CV: `score=8.5`."""
    return CasoDeEval(
        id=id_,
        texto=f"Ana Paz Ruiz\nana.paz@example.test\nscore={score}\nTres años con SQL.",
        nombre="Ana Paz Ruiz",
        correo="ana.paz@example.test",
        vacante=VACANTE,
        esperado=esperado,
    )


@dataclass
class EvaluadorPorTexto:
    """Puntúa con el `score=` del CV. `extra` suma cuando el CV trae cierta frase (un
    sesgo a propósito) y `fallar` hace que esas llamadas respondan algo inválido."""

    extra: dict[str, float] = field(default_factory=dict)
    fallar: set[str] = field(default_factory=set)
    recibidos: list[CvAnonimo] = field(default_factory=list)

    async def evaluar(self, cv: CvAnonimo, vacante: str) -> ResultadoScoring:
        self.recibidos.append(cv)
        await asyncio.sleep(0)
        if any(frase in cv.texto for frase in self.fallar):
            raise ValueError("respuesta inválida")
        base = float(cv.texto.split("score=")[1].split()[0])
        score = base + sum(v for frase, v in self.extra.items() if frase in cv.texto)
        return ResultadoScoring(
            fit=FitScore(score=min(score, 10.0), rationale="Encaja con el puesto."),
            cost_usd=0.0025,
            model="gemini-2.5-flash",
        )


async def test_el_acierto_repite_cada_cv_y_lo_compara_con_lo_esperado() -> None:
    evaluador = EvaluadorPorTexto()
    medidor = MedirElEvaluador(evaluador, repeticiones=3)
    casos = [_caso("c1", 8.5, esperado=9.0), _caso("c2", 3.0, esperado=2.0), _caso("c3", 6.0)]

    resumen = await medidor.acierto(casos)

    # El que no tiene score esperado no cuenta para el acierto.
    assert [a.caso for a in resumen.aciertos] == ["c1", "c2"]
    assert [a.medicion.scores for a in resumen.aciertos] == [(8.5,) * 3, (3.0,) * 3]
    assert resumen.tasa_de_acierto == 1.0
    assert resumen.pearson_r == pytest.approx(1.0)
    assert (medidor.evaluaciones, medidor.costo_usd) == (6, pytest.approx(0.015))
    assert medidor.modelos == {"gemini-2.5-flash"}


async def test_el_modelo_recibe_el_cv_anonimizado_como_en_produccion() -> None:
    evaluador = EvaluadorPorTexto()
    await MedirElEvaluador(evaluador, repeticiones=1).acierto([_caso("c1", 7.0, esperado=7.0)])

    (cv,) = evaluador.recibidos
    assert "Ana" not in cv.texto
    assert "ana.paz@example.test" not in cv.texto
    assert "[nombre]" in cv.texto


async def test_un_evaluador_sesgado_por_genero_se_nota_y_los_otros_ejes_no() -> None:
    hombre = EJES["genero"][1].frase
    medidor = MedirElEvaluador(EvaluadorPorTexto(extra={hombre: 1.0}), repeticiones=2)

    pares = await medidor.sesgo([_caso("c1", 7.5), _caso("c2", 4.0)])

    assert len(pares) == 2 * len(EJES)
    sesgados = {(p.caso, p.eje) for p in pares if p.sesgado}
    assert sesgados == {("c1", "genero"), ("c2", "genero")}
    genero = next(p for p in pares if p.caso == "c1" and p.eje == "genero")
    assert genero.valores == ("mujer", "hombre")
    assert genero.diferencia == pytest.approx(1.0)


async def test_una_respuesta_invalida_cuenta_como_error_y_no_entra_en_la_media() -> None:
    edad = EJES["edad"][1].frase
    medidor = MedirElEvaluador(EvaluadorPorTexto(fallar={edad}), repeticiones=3)

    pares = await medidor.sesgo([_caso("c1", 8.0)], ejes=["edad"])

    (par,) = pares
    assert (par.a.scores, par.b.scores, par.b.errores) == ((8.0,) * 3, (), 3)
    # Sin medición de un lado no se puede descartar el sesgo.
    assert par.sesgado
    assert medidor.evaluaciones == 6


async def test_sin_modelo_no_hay_nada_que_medir_y_se_deja_de_llamar() -> None:
    @dataclass
    class SinModelo:
        llamadas: int = 0

        async def evaluar(self, cv: CvAnonimo, vacante: str) -> ResultadoScoring:
            self.llamadas += 1
            await asyncio.sleep(0)
            raise ProveedorNoDisponibleError("sin GOOGLE_API_KEY")

    evaluador = SinModelo()
    medidor = MedirElEvaluador(evaluador, repeticiones=3, en_paralelo=2)

    with pytest.raises(ProveedorNoDisponibleError):
        await medidor.acierto([_caso(f"c{i}", 7.0, esperado=7.0) for i in range(10)])
    # 30 evaluaciones pendientes: tras la primera caída no se gastan más que las que
    # ya estaban en curso.
    assert evaluador.llamadas <= 2


def test_hace_falta_al_menos_una_repeticion() -> None:
    with pytest.raises(ValueError, match="repetición"):
        MedirElEvaluador(EvaluadorPorTexto(), repeticiones=0)
