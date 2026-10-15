# Marca Vortex Ops v2 · color y tipografía

> Estado: **aplicada** (2026-10-15) en la demo de clima laboral y NOM-035 (`https://ily192.github.io/Vector-HR-Tech/`), career-site, hrbp y `@vortex/ui`. Fuente: `packages/design-tokens/brand-v2.css`; `tokens.json`, el preset de Tailwind (`ink`, `aqua`, `flame`, `mist`, `risk`) y `theme.css` salen de ella. La paleta `vector-*` queda en desuso.

Es una evolución, no un cambio de marca: se mantienen las tres familias (tinta índigo, naranja y cian) y la cursiva como firma. Lo que cambia es que cada color tiene escala, rol y contraste comprobado.

## Por qué cambia

| v1 | Problema | v2 |
|---|---|---|
| Cian `#00FFFF` | Color RGB puro: vibra sobre el navy, en blanco tiene contraste 1,25:1 y lee "neón" más que "socio experto de RH" | **Aqua** `#3EECEB` sobre tinta (11,1:1) y `#066263` para texto sobre blanco (7,2:1) |
| Navy `#1E1B4B` | Es el `indigo-950` de Tailwind: genérico | **Tinta** `#181854`, más profunda y algo más azul |
| Naranja `#FF7F00` | Bien como CTA; como texto sobre blanco no llega a AA (2,9:1) | **Flame** `#FE7802` para CTA con texto en tinta (6,1:1) y `#893B01` para texto |
| Grises de Tailwind | Neutros sin relación con la marca | **Niebla**: grises con un matiz de la tinta |
| Inter + Lato | Inter es la tipografía por defecto de medio SaaS; Lato está datada y no casa con Inter | **Figtree** para todo, más JetBrains Mono para etiquetas y datos |

## Color

Escalas generadas en OKLCH (pasos perceptualmente parejos) con `packages/design-tokens/scripts/paleta_v2.py` (`python paleta_v2.py salida.json`); el contraste WCAG de cada uso está comprobado.

| Rol | Token | Hex | Uso |
|---|---|---|---|
| Tinta | `--ink-900` | `#181854` | Texto principal, superficies oscuras, botón primario |
| Tinta profunda | `--ink-950` | `#0C0C36` | Fondo del modo oscuro (cockpit) |
| Flame | `--flame-500` | `#FE7802` | CTA (con texto en tinta). Un CTA por pantalla |
| Flame texto | `--flame-700` | `#893B01` | Texto naranja sobre claro |
| Aqua | `--aqua-300` | `#3EECEB` | Acento sobre tinta: "OPS", foco, datos destacados |
| Aqua texto | `--aqua-700` | `#066263` | Enlaces e iconos sobre claro |
| Aqua foco | `--aqua-500` | `#02999B` | Anillo de foco (3:1 como elemento no textual) |
| Fondo | `--mist-50` | `#F7F8FC` | Fondo de página |
| Borde | `--mist-200` | `#DBDDE8` | Bordes y divisores |
| Texto secundario | `--mist-600` | `#686B78` | 5,3:1 sobre blanco |

Contraste mínimo: AA (4,5:1) para todo el texto, AAA para el texto de lectura.

**Degradado de marca** (flame → oro → aqua, interpolado en OKLCH): solo como acento. Sobre fondo claro **subraya**, nunca tiñe el texto, porque el extremo aqua no tiene contraste sobre blanco. Sobre tinta puede teñir titulares.

**Escala de riesgo** (NOM-035 y cualquier semáforo): relleno claro y texto oscuro del mismo tono. La claridad baja con el nivel, así que se distingue también en gris y con daltonismo, y siempre va con su etiqueta escrita.

| Nivel | Relleno | Texto | Contraste |
|---|---|---|---|
| Nulo | `#C2F3F3` | `#005256` | 7,4 |
| Bajo | `#B4EEC7` | `#02572F` | 6,7 |
| Medio | `#F8D376` | `#6F4502` | 5,8 |
| Alto | `#FFA666` | `#6F2A01` | 5,4 |
| Muy alto | `#F66D67` | `#520D0F` | 5,1 |

## Tipografía

- **Figtree** (Google Fonts, OFL, variable 300–900 con cursivas). Es la alternativa libre más cercana a la Proxima Nova que se pensó para el wordmark, cálida para un producto de personas y muy legible en UI. Una sola familia en lugar de dos: menos peso de carga y más coherencia.
- **JetBrains Mono** 500–600 para etiquetas en versalitas, códigos y datos pequeños: el guiño "Ops".
- Escala: 12 · 14 · 16 · 18 · 20 · 24 · 30 · 36 · 46. Titulares en 800 con tracking −0,03 em; texto en 400 con interlineado 1,55.
- **La cursiva es la firma**: "OPS" en el wordmark y la palabra clave de cada titular, en 800 cursiva.

## Wordmark y monograma

- Wordmark: **VORTEX** en Figtree 900 (tracking −0,03 em) + **OPS** en Figtree 800 cursiva. OPS va en `--aqua-300` sobre tinta y en `--aqua-600` sobre claro.
- Monograma (propuesta): una V en aqua sobre un cuadrado de tinta con esquinas de 9/30. Sirve como favicon e icono de app.

## Principios de UI (tendencias 2026 que adoptamos)

1. **Interfaces tranquilas**: fondo niebla, tarjetas blancas con borde de 1 px y sombras suaves, pocos colores a la vez.
2. **Tableros para decidir**: arriba lo más importante y qué hacer; el detalle se abre a demanda (*progressive disclosure*).
3. **Móvil primero para quien contesta**: una pregunta por pantalla, objetivos táctiles de 48 px o más y navegación inferior en la zona del pulgar.
4. **Explicar lo que calcula la máquina**: cada hallazgo dice qué respuestas lo explican.
5. **Accesible por defecto**: AA como mínimo, foco visible, nada que dependa solo del color y respeto a `prefers-reduced-motion`.

Radios: 10 · 14 · 20 · 28 px; los botones y chips, de cápsula.
