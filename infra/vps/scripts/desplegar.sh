#!/usr/bin/env bash
# Comando forzado de la llave de despliegue (ADR-020): con ella, GitHub Actions solo puede
# correr esto. En un servidor propio, scripts/provisionar.sh lo copia a
# /usr/local/sbin/vortex-desplegar, de root, y lo ata a la llave del usuario `despliegue`.
# En una cuenta sin root, scripts/preparar_cuenta.sh lo copia a ~/vortex/bin.
#
#   ssh <usuario>@<vps> "desplegar <commit> <usuario de GitHub>" < token
#
# El token es el GITHUB_TOKEN del job (deploy-vps.yml): llega por la entrada estándar,
# sirve para bajar las imágenes de GHCR y caduca al terminar el job. Solo se despliega
# un commit que esté en main; el repo queda en ese commit y scripts/levantar.sh hace el
# resto. Para volver atrás se corre el workflow con un commit anterior.
set -Eeuo pipefail

if [[ -z ${VORTEX_DIR:-} ]]; then
	# Servidor propio (provisionar.sh) o cuenta sin root de uno compartido (preparar_cuenta.sh).
	if [[ -d /opt/vortex ]]; then VORTEX_DIR=/opt/vortex; else VORTEX_DIR=$HOME/vortex; fi
fi
REPO=$VORTEX_DIR/repo

read -r accion version usuario resto <<<"${SSH_ORIGINAL_COMMAND:-}"
if [[ ${accion:-} != desplegar || ! ${version:-} =~ ^[0-9a-f]{40}$ ||
	! ${usuario:-} =~ ^[A-Za-z0-9][A-Za-z0-9-]{0,38}$ || -n ${resto:-} ]]; then
	echo "uso: desplegar <commit de 40 caracteres> <usuario de GitHub>" >&2
	exit 64
fi
token=""
IFS= read -r token || true
if [[ -z $token ]]; then
	echo "falta el token de GHCR por la entrada estándar" >&2
	exit 64
fi

git -C "$REPO" fetch --quiet origin main
if ! git -C "$REPO" merge-base --is-ancestor "$version" origin/main 2>/dev/null; then
	echo "$version no está en main: no se despliega" >&2
	exit 65
fi
git -C "$REPO" checkout --quiet --detach "$version"

if [[ -f $VORTEX_DIR/version.env ]]; then
	cp "$VORTEX_DIR/version.env" "$VORTEX_DIR/version.env.anterior"
fi
printf 'VERSION=%s\n' "$version" >"$VORTEX_DIR/version.env"

trap 'docker logout ghcr.io >/dev/null 2>&1 || true' EXIT
printf '%s' "$token" | docker login ghcr.io --username "$usuario" --password-stdin >/dev/null

"$REPO/infra/vps/scripts/levantar.sh"
echo "desplegado $version"
