"""Paleta de marca v2 de Vortex Ops: escalas en OKLCH y contraste WCAG de cada uso.

OKLCH da pasos perceptualmente parejos (a igual L, igual claridad aparente entre
tonos), que es lo que una escala de UI necesita. Si un color cae fuera de sRGB se
baja el croma hasta que entra, sin tocar L ni H.
"""

from __future__ import annotations

import json
import math
import sys

sys.stdout.reconfigure(encoding="utf-8")


def _oklab_a_srgb_lineal(L: float, a: float, b: float) -> tuple[float, float, float]:
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    return (
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    )


def _gamma(x: float) -> float:
    return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055


def oklch(L: float, C: float, H: float) -> str:
    """Hex sRGB; reduce el croma hasta entrar en gamut."""
    c = C
    while True:
        a, b = c * math.cos(math.radians(H)), c * math.sin(math.radians(H))
        rgb = _oklab_a_srgb_lineal(L, a, b)
        if all(-1e-4 <= v <= 1 + 1e-4 for v in rgb) or c <= 0:
            break
        c -= 0.002
    return "#" + "".join(f"{round(max(0, min(1, _gamma(max(0, v)))) * 255):02X}" for v in rgb)


def _lum(hexa: str) -> float:
    def ch(v: int) -> float:
        x = v / 255
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hexa[i : i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contraste(a: str, b: str) -> float:
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


PASOS = (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)
L_ESCALA = dict(zip(PASOS, (0.975, 0.95, 0.9, 0.82, 0.72, 0.62, 0.53, 0.45, 0.37, 0.29, 0.22)))


def escala(H: float, C_max: float, *, curva: float = 1.0) -> dict[int, str]:
    """Croma máximo a media altura y menor en los extremos (como las escalas de Radix/Tailwind 4)."""
    out = {}
    for p, L in L_ESCALA.items():
        t = 1 - abs(L - 0.6) / 0.6
        out[p] = oklch(L, C_max * max(0.12, t) ** curva, H)
    return out


paleta = {
    # Tinta: el índigo profundo de siempre, algo más azul y con más cuerpo que el indigo-950 de Tailwind.
    "ink": escala(275, 0.16),
    # Aqua: el cian eléctrico domado. El 300 es el acento sobre tinta; el 700, texto sobre blanco.
    "aqua": escala(196, 0.14),
    # Flame: el naranja de los CTA, un punto más cálido.
    "flame": escala(48, 0.2),
    # Niebla: grises con un matiz de la tinta, para que superficies y texto sean de la misma familia.
    "mist": escala(275, 0.022, curva=0.6),
    "success": escala(158, 0.15),
    "warning": escala(78, 0.16),
    "danger": escala(25, 0.2),
    "info": escala(255, 0.15),
}
# Ajustes de marca puntuales (fuera de la escala automática).
paleta["ink"][900] = oklch(0.255, 0.105, 276)  # tinta principal (antes #1E1B4B)
paleta["ink"][950] = oklch(0.19, 0.08, 276)  # fondo del cockpit en modo oscuro
paleta["aqua"][300] = oklch(0.86, 0.135, 194)  # "OPS" y acentos sobre tinta
paleta["flame"][500] = oklch(0.72, 0.19, 50)  # CTA

for nombre, esc in paleta.items():
    print(f"{nombre:8}", " ".join(f"{p}:{h}" for p, h in esc.items()))

W = "#FFFFFF"
ink = paleta["ink"][900]
usos = {
    "texto principal (ink-900) sobre blanco": (ink, W),
    "texto secundario (mist-600) sobre blanco": (paleta["mist"][600], W),
    "texto secundario (mist-600) sobre mist-50": (paleta["mist"][600], paleta["mist"][50]),
    "texto terciario (mist-500) sobre blanco": (paleta["mist"][500], W),
    "CTA: ink-900 sobre flame-500": (ink, paleta["flame"][500]),
    "enlace (aqua-700) sobre blanco": (paleta["aqua"][700], W),
    "texto naranja (flame-700) sobre blanco": (paleta["flame"][700], W),
    "acento OPS (aqua-300) sobre ink-900": (paleta["aqua"][300], ink),
    "blanco sobre ink-900": (W, ink),
    "mist-300 sobre ink-950 (texto apagado oscuro)": (paleta["mist"][300], paleta["ink"][950]),
    "borde mist-200 sobre blanco (no texto)": (paleta["mist"][200], W),
    "foco aqua-500 sobre blanco (no texto, ≥3)": (paleta["aqua"][500], W),
}
print()
for uso, (fg, bg) in usos.items():
    print(f"{contraste(fg, bg):5.2f}  {fg} sobre {bg}  {uso}")

# Escala de riesgo NOM-035: relleno claro + texto oscuro del mismo tono, la claridad baja
# con el nivel (se distingue también en escala de grises y con daltonismo).
riesgo = {
    "nulo": (oklch(0.93, 0.05, 196), oklch(0.40, 0.08, 200)),
    "bajo": (oklch(0.90, 0.08, 155), oklch(0.40, 0.10, 155)),
    "medio": (oklch(0.88, 0.12, 88), oklch(0.43, 0.10, 70)),
    "alto": (oklch(0.80, 0.14, 55), oklch(0.38, 0.11, 45)),
    "muy_alto": (oklch(0.70, 0.17, 25), oklch(0.29, 0.10, 25)),
}
print()
for k, (fondo, texto) in riesgo.items():
    print(f"riesgo {k:9} fondo {fondo} texto {texto}  contraste {contraste(texto, fondo):.2f}  L-fondo {_lum(fondo):.3f}")

json.dump({"paleta": paleta, "riesgo": riesgo}, open(sys.argv[1], "w", encoding="utf-8"), indent=1)
