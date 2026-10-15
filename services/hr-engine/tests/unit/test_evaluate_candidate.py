"""Caso de uso EvaluateCandidate con adaptadores falsos: sin base, sin red y sin mocks.

`TestComoElWorker` repite los escenarios de evaluación de `test_cv_evaluator.py`
con los mismos datos y espera lo mismo que esos tests le piden al worker: es la
red para cuando la tarea de Celery pase a llamar a este caso de uso. Los de claim
y registro del run no están aquí porque son de la tarea, no del caso de uso.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

import pytest

from app.application.evaluate_candidate import (
    EvaluateCandidate,
    NoEncontradoError,
    ResultadoEvaluacion,
)
from app.domain.entidades import Candidato, FitScore, PerfilAnonimo, Vacante
from app.domain.presupuesto import CostBudget, CostCapExceededError
from app.domain.puertos import ProveedorNoDisponibleError
from tests.unit.fakes import EmbeddingsFalsos, RepositorioEnMemoria, ScoringFalso

EMPRESA_ID = UUID("00000000-0000-0000-0000-000000000001")
VACANTE_ID = UUID("00000000-0000-0000-0000-0000000000aa")
CANDIDATO_ID = UUID("00000000-0000-0000-0000-0000000000bb")

#: La respuesta del scoring en los tests del worker.
FIT = FitScore(
    score=8.5,
    rationale="Match fuerte en Python async y Postgres",
    gaps=("sin liderazgo de equipo",),
    strengths=("python", "sqlalchemy"),
)

Evaluar = Callable[[CostBudget], Awaitable[ResultadoEvaluacion]]


def _vacante(*, icp_text: str | None = "ICP Python LATAM", tiene_embedding: bool = True) -> Vacante:
    return Vacante(
        id=VACANTE_ID,
        empresa_id=EMPRESA_ID,
        title="Senior Python",
        jd="JD",
        icp_text=icp_text,
        tiene_embedding=tiene_embedding,
    )


def _candidato(
    *, tiene_embedding: bool = True, summary: str = "10 años con Python + Postgres + async"
) -> Candidato:
    return Candidato(
        id=CANDIDATO_ID,
        full_name="Ana Dev",
        headline="Senior Python",
        summary=summary,
        tiene_embedding=tiene_embedding,
    )


def _presupuesto(*, enforce: bool = False) -> CostBudget:
    """Como en el worker: tope de 0.05 USD, que en la fase de medición no corta."""
    return CostBudget(cap_usd=0.05, enforce=enforce)


@pytest.fixture
def repo() -> RepositorioEnMemoria:
    return RepositorioEnMemoria(
        vacantes={VACANTE_ID: _vacante()}, candidatos={CANDIDATO_ID: _candidato()}
    )


@pytest.fixture
def embeddings() -> EmbeddingsFalsos:
    return EmbeddingsFalsos()


@pytest.fixture
def scoring() -> ScoringFalso:
    return ScoringFalso(fit=FIT)


@pytest.fixture
def evaluar(
    repo: RepositorioEnMemoria, embeddings: EmbeddingsFalsos, scoring: ScoringFalso
) -> Evaluar:
    caso = EvaluateCandidate(repo=repo, embeddings=embeddings, scoring=scoring)

    async def _evaluar(presupuesto: CostBudget) -> ResultadoEvaluacion:
        return await caso.ejecutar(
            vacante_id=VACANTE_ID, candidato_id=CANDIDATO_ID, presupuesto=presupuesto
        )

    return _evaluar


class TestComoElWorker:
    async def test_puntua_guarda_la_application_y_devuelve_el_resultado(
        self, evaluar: Evaluar, repo: RepositorioEnMemoria, embeddings: EmbeddingsFalsos
    ) -> None:
        """Como `test_cv_evaluator_persists_and_returns_score`."""
        presupuesto = _presupuesto()

        resultado = await evaluar(presupuesto)

        assert resultado.fit.score == 8.5
        assert resultado.fit.siguiente_paso == "entrevista"
        guardada = repo.applications[(VACANTE_ID, CANDIDATO_ID)]
        assert resultado.application_id == guardada.id
        assert guardada.empresa_id == EMPRESA_ID
        assert guardada.fit.score == 8.5
        assert guardada.fit.gaps == ("sin liderazgo de equipo",)
        assert presupuesto.breakdown == pytest.approx({"scoring": 0.0002})
        # Los dos ya tenían embedding: no se paga ninguno.
        assert embeddings.textos == []

    async def test_con_el_tope_activo_corta_antes_de_puntuar(
        self,
        evaluar: Evaluar,
        repo: RepositorioEnMemoria,
        embeddings: EmbeddingsFalsos,
        scoring: ScoringFalso,
    ) -> None:
        """Como `test_cost_cap_exceeded_marks_run_failed`: un embedding de 1 USD con un
        tope de 0.05. Lo gastado queda en el presupuesto para que la tarea lo registre."""
        repo.vacantes[VACANTE_ID] = _vacante(tiene_embedding=False)
        embeddings.costo_usd = 1.0
        presupuesto = _presupuesto(enforce=True)

        with pytest.raises(CostCapExceededError):
            await evaluar(presupuesto)

        assert presupuesto.spent_usd == pytest.approx(1.0)
        assert scoring.recibido == []
        assert repo.applications == {}

    async def test_sin_tope_el_gasto_se_mide_pero_no_corta(
        self, evaluar: Evaluar, repo: RepositorioEnMemoria, embeddings: EmbeddingsFalsos
    ) -> None:
        """Como `test_sin_tope_el_gasto_se_mide_pero_no_corta`."""
        repo.vacantes[VACANTE_ID] = _vacante(tiene_embedding=False)
        embeddings.costo_usd = 1.0
        presupuesto = _presupuesto()

        resultado = await evaluar(presupuesto)

        assert presupuesto.breakdown == pytest.approx({"embedding_icp": 1.0, "scoring": 0.0002})
        assert resultado.model == "gemini-2.5-flash"
        assert (VACANTE_ID, CANDIDATO_ID) in repo.applications

    async def test_evaluacion_a_ciegas_sin_nombre_en_lo_que_va_a_los_modelos(
        self,
        evaluar: Evaluar,
        repo: RepositorioEnMemoria,
        embeddings: EmbeddingsFalsos,
        scoring: ScoringFalso,
    ) -> None:
        """Como `test_evaluacion_a_ciegas_sin_nombre_en_el_texto_del_modelo`."""
        repo.candidatos[CANDIDATO_ID] = _candidato(
            tiene_embedding=False, summary="10 años con Python"
        )

        await evaluar(_presupuesto())

        # Ni el texto del embedding ni el perfil que se puntúa llevan "Ana Dev".
        assert embeddings.textos == ["Senior Python\n10 años con Python"]
        perfil = PerfilAnonimo(headline="Senior Python", summary="10 años con Python")
        assert scoring.recibido == [(perfil, "ICP Python LATAM")]


class TestEmbeddings:
    async def test_los_que_faltan_se_generan_y_se_guardan(
        self, evaluar: Evaluar, repo: RepositorioEnMemoria
    ) -> None:
        repo.vacantes[VACANTE_ID] = _vacante(tiene_embedding=False)
        repo.candidatos[CANDIDATO_ID] = _candidato(tiene_embedding=False)
        presupuesto = _presupuesto()

        resultado = await evaluar(presupuesto)

        assert resultado.embeddings_aplazados == ()
        assert VACANTE_ID in repo.embeddings_vacante
        assert CANDIDATO_ID in repo.embeddings_candidato
        assert set(presupuesto.breakdown) == {"embedding_icp", "embedding_candidato", "scoring"}

    async def test_sin_icp_escrito_se_usa_la_descripcion_del_puesto(
        self,
        evaluar: Evaluar,
        repo: RepositorioEnMemoria,
        embeddings: EmbeddingsFalsos,
        scoring: ScoringFalso,
    ) -> None:
        repo.vacantes[VACANTE_ID] = _vacante(icp_text=None, tiene_embedding=False)

        await evaluar(_presupuesto())

        assert embeddings.textos == ["JD"]
        assert scoring.recibido[0][1] == "JD"

    async def test_sin_proveedor_se_puntua_igual_y_quedan_aplazados(
        self, evaluar: Evaluar, repo: RepositorioEnMemoria, embeddings: EmbeddingsFalsos
    ) -> None:
        repo.vacantes[VACANTE_ID] = _vacante(tiene_embedding=False)
        repo.candidatos[CANDIDATO_ID] = _candidato(tiene_embedding=False)
        embeddings.disponible = False
        presupuesto = _presupuesto()

        resultado = await evaluar(presupuesto)

        assert resultado.embeddings_aplazados == ("icp", "candidato")
        assert repo.embeddings_vacante == {}
        assert repo.embeddings_candidato == {}
        assert (VACANTE_ID, CANDIDATO_ID) in repo.applications
        assert presupuesto.breakdown == pytest.approx({"scoring": 0.0002})

    async def test_el_tope_corta_aunque_el_proveedor_este_caido(
        self, evaluar: Evaluar, repo: RepositorioEnMemoria, embeddings: EmbeddingsFalsos
    ) -> None:
        """El tope también es `RuntimeError`, como una caída, y el worker tenía que
        distinguirlos a mano. Aquí se comprueba antes de llamar al proveedor."""
        repo.vacantes[VACANTE_ID] = _vacante(tiene_embedding=False)
        embeddings.disponible = False
        presupuesto = CostBudget(cap_usd=0.01, enforce=True)
        presupuesto.add(0.01, "previo")

        with pytest.raises(CostCapExceededError):
            await evaluar(presupuesto)

        assert embeddings.textos == []


class TestFallos:
    @pytest.mark.parametrize("falta", ["vacante", "candidato"])
    async def test_si_falta_la_vacante_o_el_candidato_falla_sin_gastar(
        self,
        falta: str,
        evaluar: Evaluar,
        repo: RepositorioEnMemoria,
        embeddings: EmbeddingsFalsos,
        scoring: ScoringFalso,
    ) -> None:
        repo.vacantes[VACANTE_ID] = _vacante(tiene_embedding=False)
        if falta == "vacante":
            del repo.vacantes[VACANTE_ID]
        else:
            del repo.candidatos[CANDIDATO_ID]
        presupuesto = _presupuesto()

        with pytest.raises(NoEncontradoError, match=f"{falta} .* no existe"):
            await evaluar(presupuesto)

        # El worker, sin candidato, ya había pagado el embedding del ICP.
        assert embeddings.textos == []
        assert scoring.recibido == []
        assert presupuesto.spent_usd == 0.0

    def test_no_encontrado_es_value_error_como_en_el_worker(self) -> None:
        # La tarea de Celery no reintenta un ValueError.
        assert issubclass(NoEncontradoError, ValueError)

    async def test_si_ningun_modelo_puede_puntuar_sale_el_error_sin_guardar_nada(
        self, evaluar: Evaluar, repo: RepositorioEnMemoria, scoring: ScoringFalso
    ) -> None:
        """La tarea aplaza la evaluación y registra lo gastado hasta ahí."""
        repo.vacantes[VACANTE_ID] = _vacante(tiene_embedding=False)
        scoring.error = ProveedorNoDisponibleError("ningún modelo disponible")
        presupuesto = _presupuesto()

        with pytest.raises(ProveedorNoDisponibleError):
            await evaluar(presupuesto)

        assert repo.applications == {}
        assert presupuesto.breakdown == pytest.approx({"embedding_icp": 0.00001})
