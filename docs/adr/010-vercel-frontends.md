# ADR-010 · Frontends deployment: Vercel + subdominio default

- **Status:** Accepted
- **Fecha:** 2026-05-25
- **Decisores:** Ilyra
- **Supersedes:** —

## Contexto

Cycle 0 + Cycle 1 requieren un target de deploy real para los frontends (`career-site`, `hrbp`) sin invertir en infra propia ni comprar dominios todavía. El plan original mencionaba Coolify VPS Hetzner ($15/mo) pero requiere ops, certificados y CD propio.

Restricciones:

- 1 dev FT, no hay tiempo para ops de infraestructura todavía.
- No queremos pagar dominio ni VPS antes de tener cliente piloto pagado.
- Necesitamos previews por PR para iteración rápida con cliente alfa (Siete).
- Los frontends son Next.js 14 (career-site) + Vite SPA (hrbp) — encajan en build serverless / static.

## Decisión

**Deployar los frontends en Vercel usando el subdominio default `*.vercel.app` durante Cycles 0-2.**

- Cada app es un proyecto Vercel separado, mismo monorepo, root directory por app.
- Free tier es suficiente: 100 GB bandwidth/mes, builds ilimitados, preview deployments por PR.
- `vercel.json` por app declara `buildCommand`, `ignoreCommand` (vía `turbo-ignore`) y headers de seguridad.
- Region `gru1` (São Paulo) para latencia LATAM.
- Dominio personalizado (`vector-hr.tech` o `vortex-ops.com`) se compra y se conecta **cuando haya revenue** (post-Cycle 4, $1.5k MRR target).

## Consecuencias

### Positivas

- Cero ops para frontends durante MVP. PR → preview URL automático con Vercel GitHub App.
- Build cache + edge CDN sin configuración. Lighthouse ≥ 85 alcanzable out-of-the-box.
- `turbo-ignore` evita rebuilds cuando no hay cambios relevantes — ahorra minutos de CI.
- Compatible con CI workflow `preview-deploy.yml` ya existente (matrix narrow a apps reales — ver tech debt fix).

### Negativas / Trade-offs

- Subdominios `*.vercel.app` no son brandeables — aceptamos costo de imagen hasta tener cliente.
- Lock-in suave: si saltamos a Cloudflare Pages o self-host, hay que reescribir `vercel.json` (10 min de trabajo, no es realmente lock-in).
- Vercel **no sirve backends Python/Node con workers persistentes**. Backends (hr-engine, agent-plane, control-plane) van a Fly.io/Railway — ver ADR-012.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Coolify VPS Hetzner | Requiere ops + certificados + CD propio. Se pospone a post-Cycle 4 cuando haya revenue. |
| Cloudflare Pages | Similar a Vercel pero Next.js App Router con runtime Node tiene fricciones en Workers. Vercel maneja Next 14 nativamente. |
| Netlify | Similar precio/UX a Vercel pero peor integración monorepo con Turbo. |
| AWS Amplify | Sobreingeniería para 2 frontends. |

## Acciones

- [x] Agregar `vercel.json` por app (`apps/career-site/vercel.json`, `apps/hrbp/vercel.json`).
- [x] `preview-deploy.yml` matrix narrow a apps existentes.
- [ ] Crear proyectos Vercel y vincular repo GitHub (requiere acción del user — repo aún no inicializado).
- [ ] Configurar env vars en Vercel UI (NEXT_PUBLIC_SUPABASE_URL, etc.) — sincronizar desde Doppler cuando el user lo provisione.
- [ ] Revisitar en Cooldown 4 (semana 12): ¿comprar dominio propio?
