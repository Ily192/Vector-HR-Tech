# @vortex/career-site

El sitio público de vacantes, hecho con Next.js 16 (App Router, Server Components) y desplegado en Vercel.

Producción: <https://vortex-career-site.vercel.app>

> Su público y su papel en el producto están en revisión en
> [ADR-017](../../docs/adr/017-career-site-modulo-gratuito.md) (Proposed): pasa a ser
> el sitio de candidatos del módulo gratuito, sin CTAs de venta.

## Cómo se corre

Desde la raíz del monorepo:

```bash
pnpm --filter @vortex/career-site dev        # http://localhost:3000
pnpm --filter @vortex/career-site test       # Vitest + Testing Library
pnpm --filter @vortex/career-site typecheck  # next typegen + tsc
```

| Variable | Para qué | Por defecto |
|---|---|---|
| `NEXT_PUBLIC_SITE_URL` | URL canónica para metadatos | URL de producción |
| `NEXT_PUBLIC_CONTACT_EMAIL` | Correo público | `hola@vectorhr.tech` |

## Estructura

```
src/
  app/            rutas: / · /vacantes · /vacantes/[slug] · /contacto
  components/     cabecera y pie, compartidos por el layout
  lib/
    vacantes.ts     acceso a vacantes (hoy, datos de ejemplo con la forma de la vista)
    site-config.ts  contacto y promesas públicas, en un solo lugar
  __tests__/
```

## Dónde van las reglas

Ver [ADR-016](../../docs/adr/016-logica-de-negocio-fuera-de-la-ui.md).

- **Qué vacante es pública** lo decide la vista `vacantes_publicas` en Supabase. El sitio no filtra por estado.
- Las páginas leen datos solo a través de `src/lib/vacantes.ts`. Conectar Supabase es cambiar ese fichero.
- Los enums se muestran con `@vortex/types/etiquetas`, nunca crudos.
- Si un texto anuncia lo que hará el backend (por ejemplo, el siguiente paso de un candidato), tiene que coincidir con `@vortex/types/reglas`.
