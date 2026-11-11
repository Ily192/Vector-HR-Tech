# syntax=docker/dockerfile:1.7
# Caddy del VPS con las plantillas de correo de Auth (ADR-020). El panel ya no va aquí:
# desde la enmienda del 2026-11-11 lo sirve Vercel. Se construye desde la raíz del
# monorepo:
#   docker build -f infra/vps/caddy/Dockerfile .
# La configuración (Caddyfile) no va en la imagen: la monta compose.yml desde el repo.
# La prueba local usa pruebas/caddy-con-panel.Dockerfile, que además trae el panel.

FROM caddy:2.11.7-alpine
COPY infra/supabase/templates /srv/plantillas
