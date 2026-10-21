# @vortex/diagnostico

El diagnóstico gratuito de vectorhrtech.com: el prospecto responde 11 preguntas y ve qué 3 procesos de HR y operaciones conviene atacar primero, con su etapa (Digitalizar, Optimizar o Automatizar) y las horas al mes que podría recuperar. Antes del detalle deja nombre, empresa y correo; el origen sale de los `utm_*` de la URL, para medir qué campaña trae clientes.

- **Preguntas y cálculo:** `src/diagnostico.ts`, sin React ni red. El cálculo se le explica entero al prospecto; lo único nuestro son los porcentajes por etapa (`PORCENTAJE_RECUPERABLE`), declarados como supuestos.
- **Guardado:** POST a `/api/diagnostico` en el mismo dominio. En el VPS, Caddy lo reenvía a la RPC `registrar_diagnostico` (migración 0017) con la clave anon; la página no lleva claves. El aviso a hola@vectorhrtech.com lo manda el hr-engine (`diagnosticos.avisar`).
- **Captcha:** Cloudflare Turnstile con `VITE_TURNSTILE_SITE_KEY`; sin ella (local y tests) no se pinta.
- **Aviso de privacidad:** `src/aviso.ts`. Faltan el responsable y la URL del aviso integral; mientras falten, la página muestra los marcadores resaltados.

## Cómo se corre

Desde la raíz del monorepo:

```bash
pnpm --filter @vortex/diagnostico dev     # http://localhost:3004
pnpm --filter @vortex/diagnostico test    # Vitest + Testing Library
pnpm --filter @vortex/diagnostico build   # tsc -b + vite build
```

En `dev`, `/api/diagnostico` va al Supabase local de la CLI: exporta `SUPABASE_LOCAL_ANON_KEY` con la clave anon de `pnpm db:status`.
