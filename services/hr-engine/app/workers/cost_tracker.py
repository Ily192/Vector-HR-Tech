"""Cost tracker per-run — enforce cost_cap_usd del run-token (ADR-005)."""

from __future__ import annotations

from dataclasses import dataclass, field


class CostCapExceeded(RuntimeError):
    """Excede el cost cap del run-token. Para inmediatamente la ejecución."""


@dataclass(slots=True)
class CostTracker:
    cap_usd: float
    spent_usd: float = 0.0
    breakdown: dict[str, float] = field(default_factory=dict)

    def add(self, amount_usd: float, label: str = "misc") -> None:
        self.spent_usd += amount_usd
        self.breakdown[label] = self.breakdown.get(label, 0.0) + amount_usd

    def assert_under_cap(self) -> None:
        if self.spent_usd >= self.cap_usd:
            raise CostCapExceeded(
                f"cost cap excedido: ${self.spent_usd:.4f} ≥ ${self.cap_usd:.4f}",
            )

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self.cap_usd - self.spent_usd)
