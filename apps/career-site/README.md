# @vortex/career-site

El sitio de vacantes para candidatos ("Vortex Empleos"), hecho con Next.js 16 (App Router, Server Components) y desplegado en Vercel.

Producción: <https://vortex-career-site.vercel.app>

> Según [ADR-017](../../docs/adr/017-career-site-modulo-gratuito.md), es el sitio de
> candidatos del módulo gratuito: muestra las vacantes de todas las empresas y no tiene
> CTAs de venta. La única puerta para empresas es su panel (`apps/hrbp`).

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
| `NEXT_PUBLIC_PANEL_EMPRESAS_URL` | Enlace "Entra a tu panel" del pie | `https://vortex-hrbp.vercel.app` |

## Estructura

```
src/
  app/            rutas: / · /vacantes (búsqueda y filtros) · /vacantes/[slug]
                  (/contacto redirige a /: la página comercial ya no existe)
  components/     cabecera, pie, buscador, filtros rápidos y tarjeta de vacante
  lib/
    vacantes.ts     Data Access Layer (server-only): hoy, datos de ejemplo con la forma de la vista
    filtros.ts      filtros en la URL: leerFiltros / urlConFiltros
    formato.ts      reexporta el formato de la vacante de @vortex/ui (compartido con hrbp)
    site-config.ts  enlaces fijos
  test/           setup y sustitutos de next/link y next/form
  __tests__/
```

## Dónde van las reglas

Ver [ADR-016](../../docs/adr/016-logica-de-negocio-fuera-de-la-ui.md).

- **Qué vacante es pública** lo decide la vista `vacantes_publicas` en Supabase. El sitio no filtra por estado.
- **El salario** solo llega si la empresa lo marcó como público (`vacantes.salario_publico`, migración 0007). Si no, la vista lo devuelve `NULL` y la tarjeta dice "Salario a convenir".
- **Los filtros** viajan en la URL y los aplica la capa de datos, no los componentes.
- Las páginas leen datos solo a través de `src/lib/vacantes.ts`. Conectar Supabase es cambiar ese fichero.
- Los enums se muestran con `@vortex/types/etiquetas`, nunca crudos.
- Si un texto anuncia lo que hará el backend (por ejemplo, el siguiente paso de un candidato), tiene que coincidir con `@vortex/types/reglas`.
