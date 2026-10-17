# @vortex/hrbp

El panel de la empresa: una SPA con Vite y React 19, desplegada en Vercel. Lo que ve cada empresa depende de los módulos de su plan ([ADR-017](../../docs/adr/017-career-site-modulo-gratuito.md)):

- **Career site (gratis):** Mis vacantes (con su cupo y Eliminar), Crear empleo (con vista previa y un brochure breve de los servicios) y el pipeline de cada vacante, abierto solo en *Aplicados*, con descarga masiva de CVs y el gancho con los números de la evaluación.
- **Servicios de IA:** además, el cockpit *Hoy* y el pipeline completo.

Producción: <https://vortex-hrbp.vercel.app> (plan gratis) y `/?plan=ia` (plan con IA). Mientras no esté conectado al hr-engine, todo son datos de ejemplo, y la barra superior lo avisa.

## Cómo se corre

Desde la raíz del monorepo:

```bash
pnpm --filter @vortex/hrbp dev        # http://localhost:3001
pnpm --filter @vortex/hrbp test       # Vitest + Testing Library
pnpm --filter @vortex/hrbp build      # tsc -b + vite build
pnpm exec size-limit                  # el bundle principal tiene un tope de 90 KB (brotli)
```

## Estructura

```
src/
  App.tsx              elige la pantalla según la URL y los módulos del plan
  navegacion/ruta.tsx  router mínimo sobre la History API (ver abajo)
  marco/marco.tsx      menú lateral, barra superior y encabezado de pantalla
  pantallas/           cockpit, mis-vacantes, crear-empleo, pipeline (un chunk cada una)
  datos/
    tipos.ts           forma de lo que devuelve el backend
    panel.ts           de dónde salen los datos (hoy, adaptador de ejemplo en memoria)
    consultas.ts       hooks de TanStack Query: las pantallas solo piden datos por aquí
  cockpit/
    resumen.ts         forma del resumen del cockpit y su ejemplo
    embudo.ts          cálculos de dibujo del embudo (puros, con test)
  test/montar.tsx      monta el panel en una URL con datos recién reiniciados
```

**Por qué no TanStack Router.** El bundle principal tiene un tope de 90 KB y React con TanStack Query ya usan 76. Con cuatro pantallas basta un router de 70 líneas (`useSyncExternalStore` + `pushState`), y cada pantalla se carga con `lazy`. Si el panel crece a rutas anidadas o con loaders, se revisa.

## Dónde van las reglas

Ver [ADR-016](../../docs/adr/016-logica-de-negocio-fuera-de-la-ui.md).

- **Indicadores** (conteos, variaciones, % del tope): los calcula el backend. `cockpit/resumen.ts` define la forma en que llegan; el componente no suma nada.
- **Límites del plan** (vacantes activas, aplicaciones por vacante, etapas habilitadas) y **números del gancho**: llegan ya decididos en `datos/tipos.ts`. La dueña es `domain/plan.py` en hr-engine. El adaptador de ejemplo los imita solo para que la demo se comporte como el producto.
- **Módulos visibles**: `sesion.modulos`, que viajará en el JWT (ADR-015).
- **Etapas del embudo y su orden**: `ETAPAS_DEL_PIPELINE` de `@vortex/types/reglas`.
- **Textos de estados, modalidades, niveles y siguiente paso**: `@vortex/types/etiquetas`.
- **Formato de salario y de fechas**: `@vortex/ui` (`formatearSalario`, `haceCuanto`), el mismo que usa el career site.
- **Importaciones**: se importa por subruta (`@vortex/types/reglas`, `/etiquetas`) y no desde la raíz, para no meter Zod en el bundle.
