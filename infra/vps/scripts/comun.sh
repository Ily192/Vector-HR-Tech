# shellcheck shell=bash
# Lo que comparten los scripts del VPS (ADR-020). Se carga con `source`, no se corre.
#
# Las rutas son las del servidor (scripts/provisionar.sh); la prueba local
# (pruebas/probar_en_local.sh) las cambia con las mismas variables.

VORTEX_DIR=${VORTEX_DIR:-/opt/vortex}
VORTEX_REPO=${VORTEX_REPO:-$VORTEX_DIR/repo}
VORTEX_ENV=${VORTEX_ENV:-$VORTEX_DIR/.env}
VORTEX_VERSION_ENV=${VORTEX_VERSION_ENV:-$VORTEX_DIR/version.env}
VORTEX_PROYECTO=${VORTEX_PROYECTO:-vortex}
VORTEX_RESPALDO_TMP=${VORTEX_RESPALDO_TMP:-/var/lib/vortex/respaldo}
# Archivos de compose extra, separados por espacios (la prueba local añade el suyo).
VORTEX_COMPOSE_EXTRA=${VORTEX_COMPOSE_EXTRA:-}
VORTEX_COMPOSE=$VORTEX_REPO/infra/vps/compose.yml
PYTHON=${PYTHON:-python3}
export VORTEX_ENV VORTEX_RESPALDO_TMP

compose() {
	local opciones=(--project-name "$VORTEX_PROYECTO" --env-file "$VORTEX_ENV") extra
	# VERSION (el commit desplegado) la escribe scripts/desplegar.sh.
	if [[ -f $VORTEX_VERSION_ENV ]]; then
		opciones+=(--env-file "$VORTEX_VERSION_ENV")
	fi
	opciones+=(-f "$VORTEX_COMPOSE")
	for extra in $VORTEX_COMPOSE_EXTRA; do
		opciones+=(-f "$extra")
	done
	docker compose "${opciones[@]}" "$@"
}

log() {
	printf '%s %s\n' "$(date -u +%H:%M:%S)" "$*" >&2
}

# El valor de una variable del .env (u otro archivo) sin cargarlo entero en el shell:
# tiene valores con espacios y no es un script.
valor_del_env() {
	sed -n "s/^$1=//p" "${2:-$VORTEX_ENV}" | tail -n 1
}

# La imagen de restic de compose.yml: restaurar.sh la usa sin compose, porque en un
# servidor nuevo el .env todavía no está completo.
imagen_de_restic() {
	sed -n 's/^[[:space:]]*image:[[:space:]]*\(restic\/restic:[^[:space:]]*\).*/\1/p' "$VORTEX_COMPOSE" | head -n 1
}
