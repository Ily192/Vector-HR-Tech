"""Reglas de la evaluación con IA del plan de pago (ADR-021).

Sin I/O: el barrido (`EvaluarAplicacionesPendientes`) las aplica y el SQL de
0014 usa los mismos números.
"""

from __future__ import annotations

#: Intentos antes de dejar una aplicación "sin evaluar" para revisarla a mano. El
#: intento se cuenta al reclamarla, así que un CV que tumbe el proceso tampoco se
#: reintenta sin fin. `resumen_de_evaluaciones()` (0014) usa el mismo número.
MAX_INTENTOS = 3

#: Un reclamo más viejo que esto es de un barrido que murió: se puede volver a tomar.
MINUTOS_DE_RECLAMO = 15


def presupuesto_agotado(gastado_usd: float, presupuesto_usd: float) -> bool:
    """Si lo gastado en evaluaciones este mes ya alcanzó el presupuesto de la plataforma.

    Al llegar, no se evalúa nada nuevo hasta el mes siguiente. El proceso de las
    empresas sigue igual: es la regla de continuidad (ADR-021 §6).
    """
    return gastado_usd >= presupuesto_usd
