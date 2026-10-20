#!/usr/bin/env bash
# Levanta o actualiza el stack en el orden que pide Supabase (ADR-020):
#   1. la base;
#   2. Auth, Storage y PostgREST: Auth y Storage corren sus propias migraciones al
#      arrancar y crean `auth.users` y `storage.buckets`;
#   3. las migraciones de Vortex (scripts/migrar.sh);
#   4. todo lo demás, y espera a que cada servicio esté sano.
# Lo corre scripts/desplegar.sh en cada despliegue; también sirve a mano tras un
# reinicio raro o una restauración. VORTEX_SIN_PULL=1 usa las imágenes que ya hay.
set -Eeuo pipefail
dir=$(dirname "${BASH_SOURCE[0]}")
# shellcheck source=comun.sh
source "$dir/comun.sh"

verificar=(--verificar)
if [[ -n ${VORTEX_LOCAL:-} ]]; then
	verificar+=(--local)
fi
"$PYTHON" "$dir/generar_secretos.py" "${verificar[@]}" "$VORTEX_ENV"

if [[ -z ${VORTEX_SIN_PULL:-} ]]; then
	log "bajando imágenes"
	compose pull --quiet
fi

log "base"
compose up -d --wait --wait-timeout 180 db
log "Auth, Storage y PostgREST"
compose up -d --wait --wait-timeout 300 auth storage rest
"$dir/migrar.sh"
log "el resto"
compose up -d --wait --wait-timeout 300 --remove-orphans
compose ps --format 'table {{.Service}}\t{{.Status}}'
log "listo"
