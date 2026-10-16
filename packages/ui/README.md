# @vortex/ui

Componentes de interfaz compartidos, con la marca v2 ([guía](../../docs/brand/branding-v2.md)). Se apoyan en `@vortex/design-tokens` y en Tailwind.

| Export | Qué es |
|---|---|
| `Button`, `buttonVariants` | Botón en cápsula. Variantes `default` (flame), `ink`, `secondary`, `ghost`, `destructive` y `link`. |
| `Card` y sus partes | Tarjeta `rounded-[20px]` con `shadow-soft` |
| `Badge`, `badgeVariants` | Etiquetas; incluye `ai` y `brand` |
| `Wordmark` | Logotipo VORTEX *OPS* / VECTOR *HR TECH*; props `brand`, `tone`, `withMark` |
| `cn` | Une clases de Tailwind sin conflictos |

## Reglas

- Solo presentación: ningún componente sabe de vacantes, candidatos ni planes. Si un componente necesita una regla de negocio, la recibe resuelta por props ([ADR-016](../../docs/adr/016-logica-de-negocio-fuera-de-la-ui.md)).
- Los colores salen de los tokens (`ink`, `aqua`, `flame`, `mist`, `risk`), nunca en hex.

```bash
pnpm --filter @vortex/ui test
```
