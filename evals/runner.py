"""Vortex skills eval runner.

Uso:
    uv run python runner.py --skill cv-evaluator --suite golden
    uv run python runner.py --skill cv-evaluator --suite golden --fail-below-threshold

Carga ejemplos desde `evals/<skill>/<suite>.jsonl`, los pasa por el modelo
configurado en `.agents/skills/<skill>/agents/<provider>.yaml`, y compara
predicciones vs ground truth.

Métrica principal por skill:
- cv-evaluator: Pearson r entre `score` predicho y `score` esperado.

Threshold de aceptación se define en `<skill>/manifest.yaml` → `thresholds`.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.table import Table
from scipy.stats import pearsonr

EVALS_DIR = Path(__file__).resolve().parent
SKILLS_DIR = EVALS_DIR.parent / ".agents" / "skills"

app = typer.Typer(help="Vortex Ops skills eval runner")
console = Console()


@dataclass(slots=True)
class EvalCase:
    id: str
    inputs: dict[str, Any]
    expected: dict[str, Any]


@dataclass(slots=True)
class EvalSummary:
    skill: str
    suite: str
    total: int
    passed: int
    failed: int
    pearson_r: float | None
    metrics: dict[str, float]


def _load_suite(skill: str, suite: str) -> list[EvalCase]:
    path = EVALS_DIR / skill / f"{suite}.jsonl"
    if not path.exists():
        return []
    cases: list[EvalCase] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        raw = json.loads(line)
        cases.append(EvalCase(id=raw["id"], inputs=raw["inputs"], expected=raw["expected"]))
    return cases


def _load_manifest(skill: str) -> dict[str, Any]:
    path = EVALS_DIR / skill / "manifest.yaml"
    if not path.exists():
        return {"thresholds": {}}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


class EvalNotWired(RuntimeError):
    """El runner no está conectado al modelo todavía."""


def _run_cv_evaluator(case: EvalCase) -> dict[str, Any]:
    """Ejecuta el skill sobre un caso y devuelve la predicción.

    NO conectado al modelo todavía (pendiente Cycle 1 wk2: integrar con
    `app.clients.scoring.score_candidate_fit`).

    La versión anterior devolvía `dict(case.expected)` en ambas ramas — con y
    sin API keys. Es decir, la predicción ERA el ground truth, así que
    `pass_rate` y `pearson_r` daban 1.0 por construcción y la suite no podía
    fallar nunca. Peor: en CI eso se habría subido como evidencia de la calidad
    del modelo. Un gate que no puede fallar es peor que no tener gate, porque
    da falsa confianza.

    Ahora falla ruidosamente. Cuando se conecte el modelo real, sustituir por
    la llamada y borrar esta excepción.
    """
    raise EvalNotWired(
        "cv-evaluator no está conectado al modelo: _run_cv_evaluator() es un "
        "stub. Integrar con app.clients.scoring.score_candidate_fit antes de "
        "usar estos evals como gate de calidad."
    )


def _eval_cv_evaluator(cases: list[EvalCase]) -> EvalSummary:
    if not cases:
        return EvalSummary(
            skill="cv-evaluator",
            suite="(empty)",
            total=0,
            passed=0,
            failed=0,
            pearson_r=None,
            metrics={},
        )
    expected_scores: list[float] = []
    predicted_scores: list[float] = []
    passed = 0
    failed = 0
    for case in cases:
        prediction = _run_cv_evaluator(case)
        expected_score = float(case.expected["score"])
        predicted_score = float(prediction["score"])
        expected_scores.append(expected_score)
        predicted_scores.append(predicted_score)
        if abs(predicted_score - expected_score) <= 1.5:
            passed += 1
        else:
            failed += 1
    r: float | None
    if len(set(expected_scores)) > 1 and len(set(predicted_scores)) > 1:
        r = float(pearsonr(expected_scores, predicted_scores).statistic)
    else:
        r = None
    return EvalSummary(
        skill="cv-evaluator",
        suite="golden",
        total=len(cases),
        passed=passed,
        failed=failed,
        pearson_r=r,
        metrics={"pass_rate": passed / len(cases)},
    )


SKILL_RUNNERS = {
    "cv-evaluator": _eval_cv_evaluator,
}


def _render_summary(summary: EvalSummary) -> None:
    table = Table(title=f"{summary.skill} · {summary.suite}")
    table.add_column("metric")
    table.add_column("value")
    table.add_row("total", str(summary.total))
    table.add_row("passed", str(summary.passed))
    table.add_row("failed", str(summary.failed))
    if summary.pearson_r is not None:
        table.add_row("pearson_r", f"{summary.pearson_r:.3f}")
    for k, v in summary.metrics.items():
        table.add_row(k, f"{v:.3f}")
    console.print(table)


@app.command()
def run(
    skill: str = typer.Option("cv-evaluator", help="Skill a evaluar"),
    suite: list[str] = typer.Option(["golden"], help="Suites a correr"),
    fail_below_threshold: bool = typer.Option(False, "--fail-below-threshold"),
) -> None:
    """Corre evals y emite código de salida 1 si threshold no alcanzado."""
    if skill not in SKILL_RUNNERS:
        console.print(f"[red]Skill {skill} sin runner registrado[/red]")
        raise typer.Exit(code=2)

    manifest = _load_manifest(skill)
    thresholds = manifest.get("thresholds", {})
    summaries: list[EvalSummary] = []
    for s in suite:
        cases = _load_suite(skill, s)
        summary = SKILL_RUNNERS[skill](cases)
        summary.suite = s
        summaries.append(summary)
        _render_summary(summary)

    if fail_below_threshold:
        min_pearson = thresholds.get("pearson_r")
        min_pass_rate = thresholds.get("pass_rate")
        min_cases = thresholds.get("min_cases", 1)
        for s in summaries:
            if s.total == 0:
                console.print(
                    f"[red]suite={s.suite}: 0 casos. Con --fail-below-threshold "
                    f"una suite vacia es un fallo, no un pase: no hay evidencia "
                    f"de calidad que medir.[/red]"
                )
                sys.exit(1)
            if s.total < min_cases:
                console.print(
                    f"[red]suite={s.suite}: {s.total} casos < min_cases={min_cases}. "
                    f"Pearson r no es estable con tan pocos.[/red]"
                )
                sys.exit(1)
            if min_pearson is not None and s.pearson_r is not None and s.pearson_r < min_pearson:
                console.print(
                    f"[red]suite={s.suite}: pearson_r={s.pearson_r:.3f} < {min_pearson}[/red]",
                )
                sys.exit(1)
            if (
                min_pass_rate is not None
                and s.metrics.get("pass_rate", 0) < min_pass_rate
            ):
                console.print(
                    f"[red]suite={s.suite}: pass_rate={s.metrics['pass_rate']:.3f} < {min_pass_rate}[/red]",
                )
                sys.exit(1)


if __name__ == "__main__":
    app()
