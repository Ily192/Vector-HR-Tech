"""El gancho del plan gratis: lo que la empresa sabe de sus CVs sin saber quién es quién.

ADR-019, que reemplaza a ADR-018. El plan gratis no usa IA. El hr-engine compara
cada CV con las skills de la vacante (`coincidencia.py`) y la empresa ve solo el
resumen: "De tus 47 CVs, 13 mencionan la mayoría de tus skills y 6, todas". Quién
es quién, ordenado por encaje y con el porqué, es la evaluación con IA, que es la
de pago.

La base aplica estas reglas en `resumen_del_gancho()` (migración 0010), y las dos
copias se prueban contra `packages/types/contracts/gancho.json`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

#: El resumen avanza de 5 en 5 CVs. Si cambiara con cada aplicación, comparar el
#: gancho antes y después de una diría qué menciona ese CV, que es justo lo que
#: se paga por ver ordenado.
TAMANO_DEL_LOTE = 5

#: Las coincidencias de una vacante cerrada se borran a estos días: el gancho ya no
#: tiene nada que mostrar (`privado.purgar_coincidencias()`, migración 0010).
DIAS_HASTA_LA_PURGA = 30


@dataclass(frozen=True, slots=True)
class ResumenDelGancho:
    revisados: int
    con_la_mayoria: int
    con_todas: int


def menciona_la_mayoria(encontradas: int, skills: int) -> bool:
    """Más de la mitad de las skills de la vacante. Incluye a los que mencionan todas."""
    return skills > 0 and encontradas * 2 > skills


def menciona_todas(encontradas: int, skills: int) -> bool:
    return skills > 0 and encontradas == skills


def resumir(encontradas: Sequence[int], skills: int) -> ResumenDelGancho:
    """Resume una vacante con `skills` skills.

    `encontradas` dice cuántas menciona cada CV, en el orden en que se revisaron.
    Solo cuentan los lotes completos; el resto espera al siguiente.
    """
    if skills == 0:
        return ResumenDelGancho(revisados=0, con_la_mayoria=0, con_todas=0)
    lote = encontradas[: len(encontradas) // TAMANO_DEL_LOTE * TAMANO_DEL_LOTE]
    return ResumenDelGancho(
        revisados=len(lote),
        con_la_mayoria=sum(1 for e in lote if menciona_la_mayoria(e, skills)),
        con_todas=sum(1 for e in lote if menciona_todas(e, skills)),
    )
