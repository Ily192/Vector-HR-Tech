"""El veredicto del revisor de vacantes con IA y su paso a marcas (ADR-022, PR 3).

El modelo lee el título y la descripción de una vacante y responde con un riesgo
(bajo, medio o alto), las frases que lo motivan y las categorías de las señales.
Este módulo define esa respuesta (el esquema que se le pide al modelo) y la convierte
en `Marca`s como las de las reglas fijas, para que `decidir()` no cambie:

- riesgo alto → marcas de gravedad alta: la vacante se rechaza y la empresa ve qué
  corregir;
- riesgo medio → marcas de gravedad media: va a revisión humana;
- riesgo bajo → ninguna marca: deciden las reglas y el contexto.

Las frases que el modelo cita se comprueban contra el texto de la vacante: si no
aparecen (el modelo no puede inventarlas), la marca queda sin cita. La prueba de
modelos (`app/cli/evals_verificador.py`) usa este mismo esquema, así que lo que se
midió es lo que corre en producción.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.domain.moderacion import Gravedad, Marca, plano

#: La regla de las marcas que pone el revisor con IA (en `motivos_moderacion`).
REGLA = "ia"

RIESGOS = ("bajo", "medio", "alto")

#: Las categorías que puede devolver el modelo (enum del esquema).
SENALES = (
    "cobro_al_candidato",
    "datos_sensibles_anticipados",
    "inversion_o_multinivel",
    "mula_de_dinero",
    "actividad_ilegal",
    "posible_trata",
    "estafa_de_tareas",
    "suplantacion_de_marca",
    "contacto_solo_mensajeria",
    "enlace_acortado",
    "sueldo_irreal",
    "oportunidad_vaga",
    "otra",
)

#: La salida estructurada que se le pide al modelo (JSON Schema).
ESQUEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "riesgo": {"type": "string", "enum": list(RIESGOS)},
        "motivos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "frase": {"type": "string"},
                    "explicacion": {"type": "string"},
                },
                "required": ["frase", "explicacion"],
                "additionalProperties": False,
            },
        },
        "senales": {"type": "array", "items": {"type": "string", "enum": list(SENALES)}},
    },
    "required": ["riesgo", "motivos", "senales"],
    "additionalProperties": False,
}

#: Qué decirle a la empresa, por categoría, cuando la vacante se rechaza o va a revisión.
CORREGIR: dict[str, str] = {
    "cobro_al_candidato": (
        "Quita cualquier cobro: postularse y empezar a trabajar no puede costarle dinero "
        "al candidato."
    ),
    "datos_sensibles_anticipados": (
        "No pidas datos bancarios, de tarjeta ni documentos antes de la entrevista."
    ),
    "inversion_o_multinivel": (
        "La bolsa de empleo es para puestos de trabajo, no para inversiones ni multinivel."
    ),
    "mula_de_dinero": "No se publican puestos que usen la cuenta del candidato para mover dinero.",
    "actividad_ilegal": "Describe con claridad las tareas del puesto y quién es el empleador.",
    "posible_trata": (
        "No se publican viajes ni trabajos en el exterior sin una empresa, contrato y "
        "condiciones verificables."
    ),
    "estafa_de_tareas": "No se publican pagos por dar likes, seguir cuentas ni escribir reseñas.",
    "suplantacion_de_marca": "Publica solo a nombre de tu propia empresa.",
    "contacto_solo_mensajeria": (
        "Agrega el nombre de tu empresa y un dato verificable (sitio web, dirección) además "
        "del WhatsApp o Telegram."
    ),
    "enlace_acortado": "Usa el enlace completo de tu empresa, no uno acortado.",
    "sueldo_irreal": "Ajusta el sueldo a lo que de verdad se paga por el puesto.",
    "oportunidad_vaga": "Describe el puesto, la empresa y las tareas concretas.",
}

#: El modelo no pudo leer la vacante (bloqueo de seguridad o negativa): decide una persona.
MARCA_BLOQUEADA = Marca(
    regla=REGLA,
    senal="La revisión automática no pudo evaluar el texto; la revisa una persona.",
    gravedad=Gravedad.MEDIA,
)

#: El revisor falló en todos los intentos (timeout, 429, 5xx, salida inválida).
MARCA_SIN_VERIFICAR = Marca(
    regla=REGLA,
    senal="No se pudo verificar automáticamente; la revisa una persona.",
    gravedad=Gravedad.MEDIA,
)

_GRAVEDAD = {"medio": Gravedad.MEDIA, "alto": Gravedad.ALTA}


class SalidaInvalidaError(ValueError):
    """La respuesta del modelo no cumple el esquema."""


class RevisionNoDisponibleError(RuntimeError):
    """El revisor no respondió (timeout, 429, 5xx o salida inválida): se reintenta."""


@dataclass(frozen=True, slots=True)
class Motivo:
    frase: str
    explicacion: str


@dataclass(frozen=True, slots=True)
class Veredicto:
    riesgo: str
    motivos: tuple[Motivo, ...]
    senales: tuple[str, ...]


def veredicto_de_json(datos: Any) -> Veredicto:
    """Valida la respuesta del modelo contra el esquema. Lanza `SalidaInvalidaError`."""
    if not isinstance(datos, Mapping):
        raise SalidaInvalidaError("la respuesta no es un objeto")
    riesgo = datos.get("riesgo")
    if riesgo not in RIESGOS:
        raise SalidaInvalidaError(f"riesgo inválido: {riesgo!r}")
    crudos = datos.get("motivos")
    senales = datos.get("senales")
    if not isinstance(crudos, list) or not isinstance(senales, list):
        raise SalidaInvalidaError("faltan motivos o señales")
    motivos: list[Motivo] = []
    for m in crudos:
        if not isinstance(m, Mapping):
            raise SalidaInvalidaError("un motivo no es un objeto")
        frase, explicacion = m.get("frase"), m.get("explicacion")
        if not isinstance(frase, str) or not isinstance(explicacion, str):
            raise SalidaInvalidaError("un motivo sin frase o explicación")
        motivos.append(Motivo(frase.strip(), explicacion.strip()))
    if any(s not in SENALES for s in senales):
        raise SalidaInvalidaError("una señal fuera de la lista")
    return Veredicto(str(riesgo), tuple(motivos), tuple(str(s) for s in senales))


def _cita(frase: str, texto: str) -> str | None:
    """La frase, solo si de verdad aparece en el texto (sin importar acentos ni mayúsculas)."""
    if not frase:
        return None
    return frase[:200] if plano(frase) in plano(texto) else None


def marcas_del_veredicto(veredicto: Veredicto, titulo: str, descripcion: str) -> list[Marca]:
    """Las marcas para `decidir()`. Un riesgo bajo no deja ninguna."""
    gravedad = _GRAVEDAD.get(veredicto.riesgo)
    if gravedad is None:
        return []
    texto = f"{titulo}\n{descripcion}"
    corregir = next((CORREGIR[s] for s in veredicto.senales if s in CORREGIR), None)
    marcas = [
        Marca(
            regla=REGLA,
            senal=m.explicacion or "La revisión automática marcó esta frase.",
            gravedad=gravedad,
            cita=_cita(m.frase, texto),
            corregir=corregir,
        )
        for m in veredicto.motivos
    ]
    if not marcas:
        marcas.append(
            Marca(
                regla=REGLA,
                senal=f"La revisión automática marcó riesgo {veredicto.riesgo}.",
                gravedad=gravedad,
                corregir=corregir,
            )
        )
    return marcas
