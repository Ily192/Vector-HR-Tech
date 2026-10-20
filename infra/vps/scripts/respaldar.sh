#!/usr/bin/env bash
# Respaldo nocturno a Cloudflare R2 con restic (ADR-020): lo cifra restic en el servidor
# antes de subirlo, y quedan 7 diarios y 4 semanales. Lo corre vortex-respaldo.timer.
#
# Cada snapshot trae lo necesario para levantar un VPS nuevo (scripts/restaurar.sh):
#   /respaldo/postgres/base.tar       copia física de la base (pg_basebackup): la que
#                                     se restaura
#   /respaldo/postgres/postgres.dump  volcado lógico (pg_dump -Fc): para sacar una tabla
#                                     o mudarse a otro Postgres
#   /respaldo/storage/                los CVs (el volumen de Storage)
#   /respaldo/db-config/              la llave de pgsodium y la config de la imagen
#   /respaldo/config/vortex.env       el .env del servidor
# Para restaurar solo hace falta RESTIC_PASSWORD y la llave de R2, guardadas fuera del
# servidor. Los domingos, además, restic revisa el 5 % de los datos.
set -Eeuo pipefail
# shellcheck source=comun.sh
source "$(dirname "${BASH_SOURCE[0]}")/comun.sh"

restic() {
	compose --profile respaldo run --rm -T respaldo "$@"
}

mkdir -p "$VORTEX_RESPALDO_TMP"
chmod 700 "$VORTEX_RESPALDO_TMP"
trap 'rm -f "$VORTEX_RESPALDO_TMP/base.tar" "$VORTEX_RESPALDO_TMP/postgres.dump"' EXIT

if ! restic cat config >/dev/null 2>&1; then
	log "repositorio nuevo en $(valor_del_env RESTIC_REPOSITORY)"
	restic init
fi

log "copia física"
compose exec -T db pg_basebackup -h /var/run/postgresql -U supabase_admin \
	-D - -F t -X fetch -c fast >"$VORTEX_RESPALDO_TMP/base.tar"
log "volcado lógico"
compose exec -T db pg_dump -h /var/run/postgresql -U supabase_admin -d postgres -F c \
	>"$VORTEX_RESPALDO_TMP/postgres.dump"
if [[ ! -s $VORTEX_RESPALDO_TMP/base.tar || ! -s $VORTEX_RESPALDO_TMP/postgres.dump ]]; then
	log "un volcado salió vacío"
	exit 1
fi

restic backup --host vortex --tag nocturno /respaldo
restic forget --host vortex --keep-daily 7 --keep-weekly 4 --prune
if [[ $(date -u +%u) == 7 ]]; then
	restic check --read-data-subset 5%
fi

ping=$(valor_del_env RESPALDO_PING_URL)
if [[ -n $ping ]]; then
	curl -fsS -m 10 --retry 3 "$ping" >/dev/null
fi
log "respaldo listo"
