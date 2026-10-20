#!/usr/bin/env bash
# Restaura el servidor desde un snapshot de restic (ADR-020).
#
#   restaurar.sh latest --si        o con el id de un snapshot (`restic snapshots`)
#
# BORRA la base, su config y los CVs actuales, y pone los del snapshot. También pone el
# .env del snapshot (el actual queda en .env.antes-de-restaurar): la base restaurada
# trae las contraseñas y el secreto JWT de ese momento.
#
# En un VPS nuevo basta con que /opt/vortex/.env tenga los valores reales de
# RESTIC_REPOSITORY, RESTIC_PASSWORD, R2_ACCESS_KEY_ID y R2_SECRET_ACCESS_KEY: restic
# corre aquí sin compose, y el resto del .env sale del snapshot. Después se despliega
# con el workflow (runbook, "Recuperar el servidor").
set -Eeuo pipefail
dir=$(dirname "${BASH_SOURCE[0]}")
# shellcheck source=comun.sh
source "$dir/comun.sh"

snapshot=${1:-}
if [[ -z $snapshot || ${2:-} != --si ]]; then
	echo "uso: restaurar.sh <snapshot|latest> --si   (borra los datos actuales)" >&2
	exit 64
fi

RESTIC_REPOSITORY=$(valor_del_env RESTIC_REPOSITORY)
RESTIC_PASSWORD=$(valor_del_env RESTIC_PASSWORD)
AWS_ACCESS_KEY_ID=$(valor_del_env R2_ACCESS_KEY_ID)
AWS_SECRET_ACCESS_KEY=$(valor_del_env R2_SECRET_ACCESS_KEY)
export RESTIC_REPOSITORY RESTIC_PASSWORD AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
restic=(docker run --rm -e RESTIC_REPOSITORY -e RESTIC_PASSWORD -e AWS_ACCESS_KEY_ID
	-e AWS_SECRET_ACCESS_KEY -e AWS_DEFAULT_REGION=auto)
if [[ -n ${VORTEX_RED_RESTIC:-} ]]; then
	restic+=(--network "$VORTEX_RED_RESTIC")
fi

# Lo bajado va a un volumen temporal: restic conserva dueños y permisos, y los
# contenedores de la base y de Storage lo leen de ahí.
temporal=${VORTEX_PROYECTO}_restaurar
docker volume rm "$temporal" >/dev/null 2>&1 || true
docker volume create "$temporal" >/dev/null
trap 'docker volume rm "$temporal" >/dev/null 2>&1 || true' EXIT

log "bajando $snapshot"
"${restic[@]}" -v "$temporal:/restaurar" "$(imagen_de_restic)" \
	restore "$snapshot" --host vortex --target /restaurar
leer() {
	docker run --rm -v "$temporal:/restaurar:ro" --entrypoint cat "$(imagen_de_restic)" \
		"/restaurar/respaldo/$1"
}
leer config/vortex.env >"$VORTEX_ENV.del-respaldo"
if ! grep -q '^POSTGRES_PASSWORD=.' "$VORTEX_ENV.del-respaldo" ||
	! docker run --rm -v "$temporal:/restaurar:ro" --entrypoint test "$(imagen_de_restic)" \
		-s /restaurar/respaldo/postgres/base.tar; then
	rm -f "$VORTEX_ENV.del-respaldo"
	log "el snapshot no trae el .env o la copia de la base"
	exit 1
fi

if [[ -f $VORTEX_ENV ]]; then
	cp -p "$VORTEX_ENV" "$VORTEX_ENV.antes-de-restaurar"
fi
install -m 600 "$VORTEX_ENV.del-respaldo" "$VORTEX_ENV"
rm -f "$VORTEX_ENV.del-respaldo"
if [[ ! -f $VORTEX_VERSION_ENV ]]; then
	# Servidor nuevo: compose necesita un VERSION; el despliegue pone el real.
	printf 'VERSION=sin-desplegar\n' >"$VORTEX_VERSION_ENV"
fi

log "deteniendo el stack"
compose --profile admin --profile respaldo down --timeout 60
for volumen in db-data db-config storage; do
	docker volume rm "${VORTEX_PROYECTO}_$volumen" >/dev/null 2>&1 || true
done

log "base"
compose run --rm --no-deps -T -v "$temporal:/restaurar:ro" --entrypoint sh db -c '
	set -e
	tar -xf /restaurar/respaldo/postgres/base.tar -C /var/lib/postgresql/data
	chown -R postgres:postgres /var/lib/postgresql/data
	chmod 700 /var/lib/postgresql/data
	cp -a /restaurar/respaldo/db-config/. /etc/postgresql-custom/'
log "CVs"
compose run --rm --no-deps -T -v "$temporal:/restaurar:ro" --entrypoint sh storage \
	-c 'cp -a /restaurar/respaldo/storage/. /var/lib/storage/'

if [[ $(valor_del_env VERSION "$VORTEX_VERSION_ENV") == sin-desplegar ]]; then
	log "datos restaurados; falta desplegar (workflow deploy-vps.yml)"
	exit 0
fi
VORTEX_SIN_PULL=1 "$dir/levantar.sh"
log "restaurado $snapshot"
