# syntax=docker/dockerfile:1.7
# Caddy con el panel (apps/hrbp) y el diagnóstico gratuito (apps/diagnostico) ya
# construidos, y las plantillas de correo de Auth (ADR-020). Se construye desde la raíz
# del monorepo:
#   docker build -f infra/vps/caddy/Dockerfile \
#     --build-arg VITE_SUPABASE_URL=https://api.<dominio> \
#     --build-arg VITE_SUPABASE_ANON_KEY=<ANON_KEY> \
#     --build-arg VITE_TURNSTILE_SITE_KEY=<site key> .
# La configuración (Caddyfile) no va en la imagen: la monta compose.yml desde el repo.

FROM node:22.23.3-alpine AS panel
ENV PNPM_HOME=/pnpm \
    HUSKY=0
RUN corepack enable
WORKDIR /repo
COPY . .
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile --filter "@vortex/hrbp..."
# Vite las mete en el bundle al construir (apps/hrbp/src/vite-env.d.ts). Sin ellas el
# panel arrancaría con los datos de ejemplo, así que el build falla en vez de eso.
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
RUN test -n "$VITE_SUPABASE_URL" && test -n "$VITE_SUPABASE_ANON_KEY" \
    || { echo "faltan VITE_SUPABASE_URL y VITE_SUPABASE_ANON_KEY" >&2; exit 1; }
RUN pnpm --filter @vortex/hrbp build

# El diagnóstico no habla con la API: manda todo a /api/diagnostico en su propio
# dominio (Caddyfile), así que no lleva VITE_SUPABASE_*. Solo la site key de Turnstile,
# que es pública; vacía (como en la prueba local) el sitio no muestra el widget.
FROM node:22.23.3-alpine AS diagnostico
ENV PNPM_HOME=/pnpm \
    HUSKY=0
RUN corepack enable
WORKDIR /repo
COPY . .
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile --filter "@vortex/diagnostico..."
ARG VITE_TURNSTILE_SITE_KEY=""
RUN pnpm --filter @vortex/diagnostico build

FROM caddy:2.11.7-alpine
COPY --from=panel /repo/apps/hrbp/dist /srv/panel
COPY --from=diagnostico /repo/apps/diagnostico/dist /srv/diagnostico
COPY infra/supabase/templates /srv/plantillas
