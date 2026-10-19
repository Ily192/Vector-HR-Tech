"""Coincidencia de skills: qué skills de la vacante menciona un CV, sin IA (ADR-019).

Es lo que alimenta el gancho del plan gratis. La empresa escribe las skills que
pide ("Python", "Inglés avanzado", "Licencia tipo B") y aquí se busca cada una en
el texto del CV, como un Ctrl+F que no se tropieza con mayúsculas, acentos,
plurales ni con las variantes de siempre ("Node.js" y "NodeJS"). No hay modelo
ni puntaje: una skill está mencionada o no, y cualquiera puede comprobarlo
leyendo el CV.

Por eso el gancho dice "mencionan" y nunca "califican". Juzgar la experiencia es
trabajo de la evaluación con IA, que es la de pago.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

#: Tope de skills por vacante y de largo de cada una. La base exige lo mismo
#: (`public.skills_validas`, migración 0010).
MAX_SKILLS = 15
MAX_LARGO_DE_SKILL = 60

#: Formas que se escriben distinto y nombran lo mismo: variantes de escritura y
#: traducciones directas. Nunca lo que una skill "implica": quien sabe
#: PostgreSQL sabe SQL, pero si su CV no dice SQL, no lo menciona. Van ya
#: normalizadas (minúsculas y sin acentos).
SINONIMOS: tuple[tuple[str, ...], ...] = (
    ("javascript", "ecmascript"),
    ("node.js", "nodejs", "node js"),
    ("react", "react.js", "reactjs"),
    ("vue", "vue.js", "vuejs"),
    ("next.js", "nextjs"),
    ("postgresql", "postgres"),
    (".net", "dotnet"),
    ("c#", "c sharp", "csharp"),
    ("c++", "cpp"),
    ("kubernetes", "k8s"),
    ("power bi", "powerbi"),
    ("aws", "amazon web services"),
    ("gcp", "google cloud", "google cloud platform"),
    ("e commerce", "ecommerce", "comercio electronico"),
    ("machine learning", "aprendizaje automatico"),
    ("inteligencia artificial", "artificial intelligence"),
    ("experiencia de usuario", "user experience", "ux"),
    ("atencion al cliente", "servicio al cliente", "customer service"),
    ("recursos humanos", "human resources", "rrhh", "rr.hh"),
    ("ingles", "english"),
    ("portugues", "portuguese"),
    ("frances", "french"),
    ("aleman", "german"),
    ("contabilidad", "accounting"),
    ("logistica", "logistics"),
    ("almacen", "warehouse"),
    ("ventas", "sales"),
)

#: Lo que separa palabras. `+` y `#` son parte de la palabra (C++, C#); `.` y `/`
#: se conservan para que "Node.js" y "CI/CD" sigan enteros, pero no la extienden.
_SEPARADORES = re.compile(r"[^\w+#./]+")
_LETRA_DE_PALABRA = r"[\w+#]"


@dataclass(frozen=True, slots=True)
class Coincidencia:
    """Las skills de la vacante que el CV menciona y las que no, en su orden."""

    encontradas: tuple[str, ...]
    faltantes: tuple[str, ...]


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y con un solo espacio entre palabras."""
    plano = _sin_acentos(texto).casefold().replace("_", " ")
    return " ".join(_SEPARADORES.sub(" ", plano).split())


def skills_validas(skills: Sequence[str]) -> bool:
    """Lo que la base acepta en `vacantes.skills`."""
    return len(skills) <= MAX_SKILLS and all(
        1 <= len(s.strip()) <= MAX_LARGO_DE_SKILL for s in skills
    )


@lru_cache(maxsize=512)
def _formas(skill: str) -> tuple[str, ...]:
    """La skill normalizada y, si tiene sinónimos, todos ellos."""
    forma = normalizar(skill)
    for grupo in SINONIMOS:
        if forma in grupo:
            return grupo
    return (forma,)


@lru_cache(maxsize=512)
def _patron(forma: str) -> re.Pattern[str]:
    """La forma como frase completa: "java" no aparece dentro de "javascript".

    Cada palabra de 3 letras o más admite el plural ("licencia" encuentra
    "licencias"). Al revés no: una skill en plural no encuentra el singular,
    porque quitar letras da falsos positivos ("sales" → "sal").
    """
    palabras = [
        re.escape(p) + ("(?:es|s)?" if p.isalpha() and len(p) >= 3 else "")
        for p in forma.split(" ")
    ]
    return re.compile(rf"(?<!{_LETRA_DE_PALABRA}){' '.join(palabras)}(?!{_LETRA_DE_PALABRA})")


def _menciona(normalizado: str, original: str, skill: str) -> bool:
    formas = _formas(skill)
    if len(formas) == 1 and len(formas[0]) <= 2:
        # "Go", "R" o "QA" en minúsculas son palabras comunes: se buscan tal como
        # las escribió la empresa, respetando mayúsculas.
        corta = _sin_acentos(skill.strip())
        return (
            re.search(
                rf"(?<!{_LETRA_DE_PALABRA}){re.escape(corta)}(?!{_LETRA_DE_PALABRA})", original
            )
            is not None
        )
    return any(_patron(f).search(normalizado) for f in formas)


def coincidir(texto_del_cv: str, skills: Sequence[str]) -> Coincidencia:
    """Qué skills de la vacante menciona el CV.

    Cada skill se mira por separado y conserva cómo la escribió la empresa: es lo
    que se guarda en `privado.coincidencias.encontradas`, que la base exige que
    sea un subconjunto de `vacantes.skills`.
    """
    normalizado = normalizar(texto_del_cv)
    original = _sin_acentos(texto_del_cv)
    encontradas: list[str] = []
    faltantes: list[str] = []
    for skill in skills:
        (encontradas if _menciona(normalizado, original, skill) else faltantes).append(skill)
    return Coincidencia(encontradas=tuple(encontradas), faltantes=tuple(faltantes))
