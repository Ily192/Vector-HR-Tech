#!/usr/bin/env bash
# Prueba el stack del VPS de punta a punta en una máquina de desarrollo (ADR-020), antes
# de llevar un cambio al servidor (runbook, "Actualizar versiones"):
#
#   1. genera un .env de prueba con scripts/generar_secretos.py --local;
#   2. construye las imágenes y levanta todo con scripts/levantar.sh;
#   3. da de alta una empresa con el comando del hr-engine, y humo.py revisa el borde;
#   4. corre contra el stack el e2e del plan gratis (`E2E_REMOTO=1 pnpm e2e:flujo`,
#      packages/e2e): invitación, vacante, 7 aplicaciones con CV, el worker del stack,
#      el gancho, el .zip y eliminar;
#   5. respalda (scripts/respaldar.sh), borra la base y los CVs, restaura
#      (scripts/restaurar.sh), comprueba que volvió todo y corre el e2e otra vez;
#   6. muestra la memoria de cada servicio y lo baja todo, volúmenes incluidos.
#
#   infra/vps/pruebas/probar_en_local.sh       (con Docker en marcha, y pnpm y uv)
#   VORTEX_SERVIDOR=1 infra/vps/pruebas/probar_en_local.sh     (en el VPS, desde un clon
#                                                               en ~/pruebas/<rama>)
#
# Usa el proyecto de compose `vortex-prueba` y 127.0.0.1:8080-8082 y :8025; no toca el
# Supabase del CLI (54321-54324). VORTEX_CONSERVAR=1 deja el stack arriba al terminar.
#
# Con VORTEX_SERVIDOR=1 (el VPS compartido, docs/runbooks/vps.md) usa 20080-20083, que son
# puertos permitidos, y no necesita pnpm, uv ni las librerías del navegador: humo.py corre
# en la imagen del hr-engine, y el e2e en la de Playwright. Los dos comparten la red de
# Caddy, así que ven los sitios en localhost, como en una máquina de desarrollo.
set -Eeuo pipefail
export MSYS_NO_PATHCONV=1

raiz=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
tmp=$(mktemp -d)
if command -v cygpath >/dev/null; then
	# Docker Desktop y Python en Windows quieren rutas C:/…, no /c/… ni /tmp/… de Git Bash.
	raiz=$(cygpath -m "$raiz")
	tmp=$(cygpath -m "$tmp")
fi
scripts=$raiz/infra/vps/scripts

export VORTEX_REPO=$raiz
export VORTEX_PROYECTO=vortex-prueba
export VORTEX_ENV=$tmp/vortex.env
export VORTEX_VERSION_ENV=$tmp/version.env
export VORTEX_RESPALDO_TMP=$tmp/respaldo
export VORTEX_COMPOSE_EXTRA=$raiz/infra/vps/pruebas/compose.local.yml
export VORTEX_RED_RESTIC=vortex-prueba_salida
export VORTEX_LOCAL=1
export PYTHON=${PYTHON:-python3}
if [[ -n ${VORTEX_SERVIDOR:-} ]]; then
	export PUERTO_PRUEBA_EMPLEOS=20080 PUERTO_PRUEBA_PANEL=20081 PUERTO_PRUEBA_API=20082
	export PUERTO_PRUEBA_MAILPIT=20083
fi
empleos=localhost:${PUERTO_PRUEBA_EMPLEOS:-8080}
panel=localhost:${PUERTO_PRUEBA_PANEL:-8081}
api=localhost:${PUERTO_PRUEBA_API:-8082}
# shellcheck source=../scripts/comun.sh
source "$scripts/comun.sh"

limpiar() {
	if [[ -z ${VORTEX_CONSERVAR:-} ]]; then
		log "bajando el stack de prueba"
		compose --profile admin --profile respaldo down --volumes --timeout 30 >/dev/null 2>&1 || true
		rm -rf "$tmp"
	else
		log "el stack sigue arriba; .env en $VORTEX_ENV"
	fi
}
trap limpiar EXIT

cat >"$VORTEX_ENV" <<EOF
DOMINIO_EMPLEOS=$empleos
DOMINIO_PANEL=$panel
DOMINIO_API=$api
ESQUEMA_PUBLICO=http
SMTP_ADMIN_EMAIL=no-responder@vortex.test
RESTIC_REPOSITORY=s3:http://s3:9000/respaldos
R2_ACCESS_KEY_ID=prueba-local
R2_SECRET_ACCESS_KEY=prueba-local-secreta
EOF
"$PYTHON" "$scripts/generar_secretos.py" --local "$VORTEX_ENV"
printf 'VERSION=prueba\n' >"$VORTEX_VERSION_ENV"

log "construyendo las imágenes"
compose build --quiet
VORTEX_SIN_PULL=1 "$scripts/levantar.sh"

# En el servidor, humo.py y el e2e corren en un contenedor con la red de Caddy, con el
# usuario 0, que en Docker sin root es la propia cuenta: así escriben en $tmp y en el repo.
en_la_red_de_caddy() {
	docker run --rm --network "container:$(compose ps --quiet caddy)" --user 0:0 "$@"
}

# humo.py, con el entorno del hr-engine, que trae httpx.
uv=(uv)
if ! command -v uv >/dev/null; then
	uv=("$PYTHON" -m uv)
fi
humo() {
	if [[ -n ${VORTEX_SERVIDOR:-} ]]; then
		en_la_red_de_caddy -v "$raiz/infra/vps/pruebas:/pruebas:ro" -v "$tmp:$tmp" \
			-e MAILPIT_URL=http://mailpit:8025 vortex-local/hr-engine:prueba \
			python /pruebas/humo.py "$VORTEX_ENV" "$@"
		return
	fi
	(cd "$raiz/services/hr-engine" &&
		"${uv[@]}" run --quiet python "$raiz/infra/vps/pruebas/humo.py" "$VORTEX_ENV" "$@")
}
# El e2e entra con generate_link y la clave secreta (solo en esta variable), y espera al
# beat del stack, como contra un despliegue.
e2e() {
	local variables=(
		E2E_REMOTO=1 "E2E_CORREO=$correo"
		"E2E_CAREER_SITE_URL=http://$empleos" "E2E_PANEL_URL=http://$panel"
		"E2E_SUPABASE_URL=http://$api"
		"E2E_SUPABASE_PUBLISHABLE_KEY=$(valor_del_env ANON_KEY)"
		"E2E_SUPABASE_SECRET_KEY=$(valor_del_env SERVICE_ROLE_KEY)"
	)
	if [[ -z ${VORTEX_SERVIDOR:-} ]]; then
		env "${variables[@]}" pnpm --dir "$raiz" e2e:flujo
		return
	fi
	# La imagen de Playwright de la versión del lockfile, que trae el navegador y sus librerías.
	local version opciones=()
	version=$(grep -oE "'@playwright/test@[0-9.]+'" "$raiz/pnpm-lock.yaml" | head -1 | tr -dc '0-9.' | sed 's/^\.*//')
	for variable in "${variables[@]}"; do opciones+=(-e "$variable"); done
	en_la_red_de_caddy "${opciones[@]}" -e CI=1 -v "$raiz:$raiz" -w "$raiz" --ipc=host \
		"mcr.microsoft.com/playwright:v$version-noble" bash -c \
		'corepack enable && pnpm install --frozen-lockfile --filter "@vortex/e2e..." && pnpm e2e:flujo'
}

correo="rh-$(date +%s)@andes.test"
compose exec -T hr-engine-api python -m app.cli.alta_empresa \
	--empresa "Andes Logística" --correo "$correo" --nombre "Mariana Ruiz" --tamano 35
humo borde "$correo"
log "e2e del plan gratis contra el stack"
e2e

humo foto "$tmp/foto.json"
log "respaldo"
"$scripts/respaldar.sh"
log "restauración (borra la base y los CVs de la prueba)"
"$scripts/restaurar.sh" latest --si
humo comparar "$tmp/foto.json"
log "e2e otra vez, sobre la base restaurada"
e2e

log "memoria"
mapfile -t contenedores < <(compose ps --quiet)
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' "${contenedores[@]}"
