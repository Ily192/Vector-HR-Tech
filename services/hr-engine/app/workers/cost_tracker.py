"""Cost tracker per-run: mide el gasto y, si se activa, aplica el cost_cap_usd (ADR-005).

Desde 2026-10 el tope está APAGADO por defecto (`ENFORCE_RUN_COST_CAP=false`):
Ilyra quiere medir cuánto cuesta de verdad cada ejecución antes de fijar un
número. El gasto se sigue sumando y guardando igual; `enforce` solo decide si
superar el cap corta la ejecución.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class CostCapExceededError(RuntimeError):
    """Excede el cost cap del run-token. Para inmediatamente la ejecución."""


@dataclass(slots=True)
class CostTracker:
    cap_usd: float
    #: False = solo medir. El cap se registra pero no corta nada.
    enforce: bool = True
    spent_usd: float = 0.0
    breakdown: dict[str, float] = field(default_factory=dict)

    def add(self, amount_usd: float, label: str = "misc") -> None:
        self.spent_usd += amount_usd
        self.breakdown[label] = self.breakdown.get(label, 0.0) + amount_usd

    def assert_under_cap(self) -> None:
        if not self.enforce:
            return
        if self.spent_usd >= self.cap_usd:
            raise CostCapExceededError(
                f"cost cap excedido: ${self.spent_usd:.4f} ≥ ${self.cap_usd:.4f}",
            )

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.cap_usd - self.spent_usd)
