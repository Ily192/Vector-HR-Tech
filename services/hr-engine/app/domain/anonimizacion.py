"""El texto del CV sin lo que identifica o discrimina, antes de mandarlo al modelo (ADR-021 §3).

Es la mitad de "a ciegas": la otra es el SKILL.md de cv-evaluator, que prohíbe
inferir o usar datos personales. Con reglas no se atrapa todo (un "34 años" suelto
en un párrafo, por ejemplo), y por eso van las dos.

Se quita:
- el nombre del candidato y cada una de sus partes, sin importar mayúsculas ni acentos;
- los correos, los teléfonos y los enlaces;
- las líneas de datos personales: edad o fecha de nacimiento, sexo o género, estado
  civil, nacionalidad, dirección o domicilio, religión, discapacidad, hijos y
  documentos de identidad.

Lo que se quita queda marcado (`[nombre]`, `[correo]`…), para que el modelo sepa que
ahí había algo y no lo cuente como un hueco del CV.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

#: Unas 3.000 palabras, un CV de 4 o 5 páginas. Acota lo que cuesta cada evaluación.
MAX_CARACTERES = 12_000

NOMBRE = "[nombre]"
CORREO = "[correo]"
TELEFONO = "[teléfono]"
ENLACE = "[enlace]"

#: Partículas de los nombres compuestos ("María de la Cruz"): son palabras comunes.
_PARTICULAS = frozenset(
    {
        "de",
        "del",
        "la",
        "las",
        "los",
        "y",
        "e",
        "da",
        "das",
        "do",
        "dos",
        "di",
        "du",
        "van",
        "von",
        "der",
        "san",
        "santa",
    }
)

#: Cada letra sin acento y las formas con acento que puede tener en un CV.
_VARIANTES = {
    "a": "aáàäâã",
    "e": "eéèëê",
    "i": "iíìïî",
    "o": "oóòöôõ",
    "u": "uúùüû",
    "n": "nñ",
    "c": "cç",
}

_CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_ENLACE = re.compile(
    r"(?:https?://|www\.)\S+"
    r"|\b[\w-]+\.(?:com|net|org|io|dev|me|mx|co|ve|ar|cl|pe|es|br)(?:\.[a-z]{2})?/\S*",
    re.IGNORECASE,
)
#: Dígitos con espacios, puntos, guiones o paréntesis entre medio. Cuántos dígitos
#: hacen un teléfono lo decide `_es_telefono`.
_NUMERO = re.compile(r"(?<![\w+])\+?\(?\d[\d\s().-]{6,}\d(?!\w)")
#: "2018 - 2022" o "2015-2019 · 2020" son fechas de experiencia, no un teléfono.
_SOLO_ANIOS = re.compile(r"^(?:(?:19|20)\d{2}\D*)+$")
_MIN_DIGITOS_DE_TELEFONO = 9
_MAX_DIGITOS_DE_TELEFONO = 15

#: El comienzo de una línea de datos personales, ya sin acentos y en minúsculas. Pide
#: separador (":" o guion) para no llevarse "Dirección de proyectos" o "Edad de oro".
_DATO_PERSONAL = re.compile(
    r"^\W*(?:edad|fecha de nacimiento|f\. de nacimiento|lugar de nacimiento|nacimiento"
    r"|sexo|genero|estado civil|nacionalidad|direccion|domicilio|religion|discapacidad"
    r"|hijos|curp|rfc|nss|imss|dni|cedula|pasaporte|ine"
    # "\u2013" es la raya corta que Word pone en lugar del guion.
    r"|numero de seguridad social|seguro social)\s*[:\-\u2013]"
)


@dataclass(frozen=True, slots=True)
class CvAnonimo:
    """El texto que sí puede llegar al modelo. Solo lo crea `anonimizar`."""

    texto: str
    #: Si se cortó por pasar de `MAX_CARACTERES`.
    recortado: bool = False


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def _es_telefono(coincidencia: re.Match[str]) -> bool:
    numero = coincidencia.group(0)
    digitos = sum(c.isdigit() for c in numero)
    if not _MIN_DIGITOS_DE_TELEFONO <= digitos <= _MAX_DIGITOS_DE_TELEFONO:
        return False
    return not _SOLO_ANIOS.match(numero.strip())


def _partes_del_nombre(nombre: str) -> list[str]:
    """Las partes que se buscan en el CV, de la más larga a la más corta."""
    partes = {p for p in re.split(r"[\s\-]+", nombre.strip()) if p}
    return sorted(
        (p for p in partes if len(p) >= 2 and p.casefold() not in _PARTICULAS),
        key=len,
        reverse=True,
    )


def _patron_de_parte(parte: str) -> re.Pattern[str]:
    # Las partes de dos letras ("Li", "Wu") solo tal como se escriben: en minúsculas
    # son sílabas de cualquier palabra.
    if len(parte) == 2:
        return re.compile(rf"(?<!\w){re.escape(parte)}(?!\w)")
    letras = _sin_acentos(parte).casefold()
    clase = "".join(f"[{_VARIANTES[c]}]" if c in _VARIANTES else re.escape(c) for c in letras)
    return re.compile(rf"(?<!\w){clase}(?!\w)", re.IGNORECASE)


def _recortar(texto: str) -> tuple[str, bool]:
    if len(texto) <= MAX_CARACTERES:
        return texto, False
    corte = texto.rfind("\n", 0, MAX_CARACTERES)
    # Sin un salto de línea razonablemente cerca, se corta en seco.
    if corte < MAX_CARACTERES * 0.8:
        corte = MAX_CARACTERES
    return texto[:corte].rstrip(), True


def anonimizar(texto: str, *, nombre: str | None, correo: str | None = None) -> CvAnonimo:
    """El CV listo para el modelo: sin datos personales y con el largo acotado."""
    lineas = [
        linea
        for linea in texto.splitlines()
        if not _DATO_PERSONAL.match(_sin_acentos(linea).casefold())
    ]
    limpio = "\n".join(lineas)
    if correo:
        limpio = limpio.replace(correo, CORREO)
    limpio = _CORREO.sub(CORREO, limpio)
    limpio = _ENLACE.sub(ENLACE, limpio)
    limpio = _NUMERO.sub(lambda m: TELEFONO if _es_telefono(m) else m.group(0), limpio)
    for parte in _partes_del_nombre(nombre or ""):
        limpio = _patron_de_parte(parte).sub(NOMBRE, limpio)
    # Varios marcadores seguidos ("[nombre] [nombre]") dicen lo mismo que uno.
    marcador = re.escape(NOMBRE)
    limpio = re.sub(rf"{marcador}(?:[ \t,]+{marcador})+", NOMBRE, limpio)
    limpio = re.sub(r"\n{3,}", "\n\n", limpio).strip()
    recortado, se_corto = _recortar(limpio)
    return CvAnonimo(texto=recortado, recortado=se_corto)
