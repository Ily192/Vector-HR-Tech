# syntax=docker/dockerfile:1.7
# Career site (apps/career-site) como servidor Node con `output: "standalone"` de
# Next.js (ADR-020). Se construye desde la raíz del monorepo:
#   docker build -f infra/vps/career-site/Dockerfile \
#     --build-arg NEXT_PUBLIC_SITE_URL=https://empleos.<dominio> \
#     --build-arg NEXT_PUBLIC_PANEL_EMPRESAS_URL=https://panel.<dominio> .
# Supabase y Turnstile se leen en el servidor al arrancar (compose.yml), no aquí.

FROM node:22.23.4-alpine AS build
ENV PNPM_HOME=/pnpm \
    HUSKY=0 \
    NEXT_TELEMETRY_DISABLED=1 \
    NEXT_OUTPUT=standalone
RUN corepack enable
WORKDIR /repo
COPY . .
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile --filter "@vortex/career-site..."
# NEXT_PUBLIC_* se escriben en el bundle al construir.
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_PANEL_EMPRESAS_URL
ARG NEXT_PUBLIC_TURNSTILE_SITE_KEY=""
RUN test -n "$NEXT_PUBLIC_SITE_URL" && test -n "$NEXT_PUBLIC_PANEL_EMPRESAS_URL" \
    || { echo "faltan NEXT_PUBLIC_SITE_URL y NEXT_PUBLIC_PANEL_EMPRESAS_URL" >&2; exit 1; }
RUN pnpm --filter @vortex/career-site build

# El servidor mínimo de Next con los archivos que trazó el build, y `.next/static`, que
# `standalone` no copia solo (docs de Next 16: output, "Automatically Copying Traced
# Files"). El sitio no tiene carpeta `public`.
FROM node:22.23.4-alpine
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
WORKDIR /app
COPY --from=build --chown=node:node /repo/apps/career-site/.next/standalone ./
COPY --from=build --chown=node:node /repo/apps/career-site/.next/static ./apps/career-site/.next/static
USER node
EXPOSE 3000
CMD ["node", "apps/career-site/server.js"]
