# @vortex/ui

Componentes de interfaz compartidos, con la marca v2 ([guía](../../docs/brand/branding-v2.md)). Se apoyan en `@vortex/design-tokens` y en Tailwind.

| Export | Qué es |
|---|---|
| `Button`, `buttonVariants` | Botón en cápsula. Variantes `default` (flame), `ink`, `secondary`, `ghost`, `destructive` y `link`. |
| `Card` y sus partes | Tarjeta `rounded-[20px]` con `shadow-soft` |
| `Badge`, `badgeVariants` | Etiquetas; incluye `ai` y `brand` |
| `Wordmark` | Logotipo VORTEX *OPS* / VECTOR *HR TECH*; props `brand`, `tone`, `withMark` |
| `cn` | Une clases de Tailwind sin conflictos. Úsalo también con `buttonVariants()` en un enlace: sin él, `border-transparent` le gana al borde de `secondary`. |
| `formatearSalario`, `haceCuanto`, `esNueva`, `iniciales` | Cómo se escriben el salario, la fecha de publicación y el monograma de una vacante. Las usan el career site y el panel de la empresa. |

## Reglas

- Solo presentación: ningún componente sabe de candidatos ni planes, y el formato de la vacante solo dice cómo se escribe un dato, no si se muestra. Si un componente necesita una regla de negocio, la recibe resuelta por props ([ADR-016](../../docs/adr/016-logica-de-negocio-fuera-de-la-ui.md)).
- Los colores salen de los tokens (`ink`, `aqua`, `flame`, `mist`, `risk`), nunca en hex.

```bash
pnpm --filter @vortex/ui test
```
