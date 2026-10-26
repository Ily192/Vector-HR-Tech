#!/usr/bin/env bash
# Prepara Vortex en una cuenta sin root de un servidor compartido (ADR-020, enmienda del
# 2026-10-22): el VPS de Contabo, donde también corre Coolify y el administrador del
# servidor le da a Vortex un usuario con Docker sin root, sin sudo y con topes de memoria
# y CPU. En un servidor propio se usa scripts/provisionar.sh, que corre como root.
#
# Una vez, como ese usuario, desde la raíz del repo en la máquina de Ilyra (runbook
# docs/runbooks/vps.md, paso 3):
#
#   scp infra/vps/scripts/preparar_cuenta.sh ilyra@<ip>:
#   ssh ilyra@<ip> bash preparar_cuenta.sh "<llave pública de despliegue>"
#
# Deja, todo dentro de la cuenta: el repo en ~/vortex/repo; la llave de despliegue en
# ~/.ssh/authorized_keys, atada a ~/vortex/bin/vortex-desplegar; el comando `vortex` en
# ~/.local/bin; el respaldo nocturno como timer de systemd del usuario, y el .env con sus
# secretos generados. Lo de sistema (parches, fail2ban, ufw, swap, el demonio de Docker)
# es del administrador del servidor.
# Se puede volver a correr: deja la cuenta en el mismo estado y no pisa el .env.
set -Eeuo pipefail

LLAVE_DESPLIEGUE=${1:-}
REPO_URL=${VORTEX_REPO_URL:-https://github.com/Ily192/Vector-HR-Tech.git}
DIR=$HOME/vortex

falla() {
	echo "preparar_cuenta: $*" >&2
	exit 1
}
paso() {
	printf '\n== %s\n' "$*"
}

[[ $EUID -ne 0 ]] || falla "esto es para una cuenta sin root; en un servidor propio, provisionar.sh"
[[ $LLAVE_DESPLIEGUE =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ [^\"]*)?$ ]] ||
	falla "uso: preparar_cuenta.sh \"<llave pública de despliegue, ssh-ed25519 en una línea>\""

paso "lo que pone el administrador"
command -v git >/dev/null || falla "falta git"
command -v python3 >/dev/null || falla "falta python3"
docker info >/dev/null 2>&1 || falla "Docker no responde para $(id -un)"
docker compose version >/dev/null || falla "falta el plugin de docker compose"
# Sin linger, los contenedores y el timer se detienen al cerrar la última sesión.
[[ $(loginctl show-user "$(id -un)" -p Linger --value 2>/dev/null) == yes ]] ||
	falla "la cuenta no tiene linger: pídele al administrador loginctl enable-linger $(id -un)"
echo "Docker $(docker version --format '{{.Server.Version}}'), $(docker info --format '{{.SecurityOptions}}' | grep -o rootless || echo 'con root')"

paso "el repo en $DIR/repo"
install -d -m 700 "$DIR" "$DIR/bin" "$DIR/respaldo-tmp"
if [[ ! -d $DIR/repo/.git ]]; then
	git clone --quiet "$REPO_URL" "$DIR/repo"
fi
git -C "$DIR/repo" fetch --quiet origin main

paso "la llave de despliegue"
# Una copia fuera del repo: el despliegue cambia el repo de commit, no lo que corre su llave.
install -m 700 "$DIR/repo/infra/vps/scripts/desplegar.sh" "$DIR/bin/vortex-desplegar"
install -d -m 700 "$HOME/.ssh"
touch "$HOME/.ssh/authorized_keys"
chmod 600 "$HOME/.ssh/authorized_keys"
cuerpo=$(cut -d' ' -f2 <<<"$LLAVE_DESPLIEGUE")
linea="restrict,command=\"$DIR/bin/vortex-desplegar\" $LLAVE_DESPLIEGUE"
# Solo se toca la línea de esta llave; las demás (la de Ilyra) se quedan como están.
grep -vF "$cuerpo" "$HOME/.ssh/authorized_keys" >"$HOME/.ssh/authorized_keys.nuevo" || true
printf '%s\n' "$linea" >>"$HOME/.ssh/authorized_keys.nuevo"
chmod 600 "$HOME/.ssh/authorized_keys.nuevo"
mv "$HOME/.ssh/authorized_keys.nuevo" "$HOME/.ssh/authorized_keys"

paso "el comando vortex"
install -d "$HOME/.local/bin"
cat >"$HOME/.local/bin/vortex" <<'EOF'
#!/usr/bin/env bash
# docker compose del stack de Vortex con su .env y su versión (ADR-020):
#   vortex ps · vortex logs -f auth · vortex --profile admin up -d studio
source "$HOME/vortex/repo/infra/vps/scripts/comun.sh"
cd "$VORTEX_DIR"
compose "$@"
EOF
chmod 755 "$HOME/.local/bin/vortex"

paso "respaldo nocturno (08:00 UTC), con el systemd del usuario"
unidades=$HOME/.config/systemd/user
install -d "$unidades"
# La unidad del repo es la de sistema (User=, /opt/vortex); aquí va la de la cuenta.
cat >"$unidades/vortex-respaldo.service" <<'EOF'
# Respaldo nocturno de Vortex a Cloudflare R2 (ADR-020). Lo instala
# infra/vps/scripts/preparar_cuenta.sh; lo dispara vortex-respaldo.timer.
#   systemctl --user start vortex-respaldo     (a mano)
#   journalctl --user -u vortex-respaldo       (cómo le fue)
[Unit]
Description=Respaldo de Vortex a R2 (restic)
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=%h/vortex/repo/infra/vps/scripts/respaldar.sh
Nice=10
EOF
install -m 644 "$DIR/repo/infra/vps/systemd/vortex-respaldo.timer" "$unidades/"
systemctl --user daemon-reload
systemctl --user enable --now --quiet vortex-respaldo.timer

paso ".env de $DIR"
if [[ ! -f $DIR/.env ]]; then
	python3 "$DIR/repo/infra/vps/scripts/generar_secretos.py" "$DIR/.env"
	# El administrador reserva a la cuenta los puertos desde el 20000.
	sed -i 's/^PUERTO_STUDIO=.*/PUERTO_STUDIO=20000/; s/^PUERTO_DB=.*/PUERTO_DB=20001/' "$DIR/.env"
	chmod 600 "$DIR/.env"
else
	echo "ya existe: no se toca"
fi

cat <<EOF

Listo. Después, siguiendo el runbook:
  1. Llenar lo que falta:  nano ~/vortex/.env
     y comprobar:          python3 ~/vortex/repo/infra/vps/scripts/generar_secretos.py --verificar ~/vortex/.env
  2. Guardar RESTIC_PASSWORD en el gestor de contraseñas.
  3. ANON_KEY para GitHub: python3 ~/vortex/repo/infra/vps/scripts/generar_secretos.py --clave-publica ~/vortex/.env
  4. En GitHub, la variable VPS_USUARIO=$(id -un), y correr el workflow "Deploy VPS (Contabo)".
EOF
