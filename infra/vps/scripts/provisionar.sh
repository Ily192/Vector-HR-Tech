#!/usr/bin/env bash
# Prepara un VPS nuevo de Contabo con Ubuntu LTS para Vortex (ADR-020). Una vez, como
# root, desde la raíz del repo en la máquina de Ilyra (runbook docs/runbooks/vps.md, paso 3):
#
#   scp infra/vps/scripts/provisionar.sh root@<ip>:/root/
#   ssh root@<ip> bash /root/provisionar.sh <usuario> "<llave pública de despliegue>"
#
# Deja: el usuario <usuario> con sudo y la misma llave que root; el usuario
# `despliegue`, cuya llave solo puede correr vortex-desplegar; SSH solo con llave y sin
# root; parches automáticos; fail2ban; ufw con solo SSH; 2 GB de swap; Docker del
# repositorio oficial con rotación de logs; el repo en /opt/vortex/repo; el .env con sus
# secretos generados, y el respaldo nocturno.
# Se puede volver a correr: deja el servidor en el mismo estado y no pisa el .env.
set -Eeuo pipefail

ADMIN=${1:-}
LLAVE_DESPLIEGUE=${2:-}
REPO_URL=${VORTEX_REPO_URL:-https://github.com/Ily192/Vector-HR-Tech.git}

falla() {
	echo "provisionar: $*" >&2
	exit 1
}
paso() {
	printf '\n== %s\n' "$*"
}

[[ $EUID -eq 0 ]] || falla "córrelo como root"
[[ $ADMIN =~ ^[a-z_][a-z0-9_-]{0,31}$ && $ADMIN != despliegue ]] ||
	falla "uso: provisionar.sh <usuario> \"<llave pública de despliegue>\""
[[ $LLAVE_DESPLIEGUE =~ ^ssh-ed25519\ [A-Za-z0-9+/=]+(\ [^\"]*)?$ ]] ||
	falla "la llave de despliegue tiene que ser una ssh-ed25519 en una línea"
[[ -s /root/.ssh/authorized_keys ]] || falla "root no tiene llave SSH: instálale la tuya (runbook, paso 2)"
# shellcheck source=/dev/null
source /etc/os-release
[[ $ID == ubuntu ]] || falla "pensado para Ubuntu LTS (este es $PRETTY_NAME)"

paso "paquetes y parches"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get -y -q -o Dpkg::Options::=--force-confold upgrade
apt-get -y -q install ca-certificates curl git ufw fail2ban unattended-upgrades python3

paso "hora en UTC"
timedatectl set-timezone UTC

paso "swap de 2 GB"
if ! swapon --show=NAME --noheadings | grep -qx /swapfile; then
	if [[ ! -f /swapfile ]]; then
		fallocate -l 2G /swapfile
		chmod 600 /swapfile
		mkswap /swapfile >/dev/null
	fi
	swapon /swapfile
fi
grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >>/etc/fstab
# Que la swap sea el último recurso, no la memoria de todos los días.
echo 'vm.swappiness=10' >/etc/sysctl.d/60-vortex.conf
sysctl -q -p /etc/sysctl.d/60-vortex.conf

paso "usuarios: $ADMIN y despliegue"
id "$ADMIN" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$ADMIN"
usermod -aG sudo "$ADMIN"
# Sin contraseña: no hay ninguna que adivinar, y quien tiene la llave ya es admin (y
# Docker equivale a root). Para la consola VNC de Contabo, ver el runbook.
echo "$ADMIN ALL=(ALL) NOPASSWD:ALL" >/etc/sudoers.d/90-vortex-admin
chmod 440 /etc/sudoers.d/90-vortex-admin
visudo -cqf /etc/sudoers.d/90-vortex-admin
install -d -m 700 -o "$ADMIN" -g "$ADMIN" "/home/$ADMIN/.ssh"
install -m 600 -o "$ADMIN" -g "$ADMIN" /root/.ssh/authorized_keys "/home/$ADMIN/.ssh/authorized_keys"

id despliegue >/dev/null 2>&1 || adduser --disabled-password --gecos "" despliegue
install -d -m 700 -o despliegue -g despliegue /home/despliegue/.ssh
# `restrict`: sin reenvío de puertos ni terminal. `command`: solo vortex-desplegar.
printf 'restrict,command="/usr/local/sbin/vortex-desplegar" %s\n' "$LLAVE_DESPLIEGUE" \
	>/home/despliegue/.ssh/authorized_keys
chown despliegue:despliegue /home/despliegue/.ssh/authorized_keys
chmod 600 /home/despliegue/.ssh/authorized_keys

paso "SSH: solo llaves y sin root"
# 00-: sshd se queda con el primer valor que lee, y la imagen trae su 50-cloud-init.conf.
cat >/etc/ssh/sshd_config.d/00-vortex.conf <<EOF
# Vortex (ADR-020), de infra/vps/scripts/provisionar.sh.
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
AuthenticationMethods publickey
X11Forwarding no
MaxAuthTries 3
LoginGraceTime 30
AllowUsers $ADMIN despliegue
EOF
sshd -t
systemctl reload ssh 2>/dev/null || systemctl restart ssh

paso "Docker (repositorio oficial, docs.docker.com/engine/install/ubuntu)"
if ! command -v docker >/dev/null; then
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
	chmod a+r /etc/apt/keyrings/docker.asc
	cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
	apt-get update -q
	apt-get -y -q install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
# Logs rotados, y los contenedores siguen vivos si se reinicia el demonio (parches).
cat >/etc/docker/daemon.json.nuevo <<'EOF'
{
  "log-driver": "local",
  "log-opts": { "max-size": "10m", "max-file": "5" },
  "live-restore": true
}
EOF
if ! cmp -s /etc/docker/daemon.json.nuevo /etc/docker/daemon.json; then
	mv /etc/docker/daemon.json.nuevo /etc/docker/daemon.json
	systemctl restart docker
else
	rm /etc/docker/daemon.json.nuevo
fi
systemctl enable --quiet docker
usermod -aG docker "$ADMIN"
usermod -aG docker despliegue

paso "parches automáticos"
cat >/etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
cat >/etc/apt/apt.conf.d/52vortex-unattended-upgrades <<'EOF'
// Vortex (ADR-020): si un parche pide reinicio, a las 3 a. m. de Ciudad de México.
Unattended-Upgrade::Automatic-Reboot "true";
Unattended-Upgrade::Automatic-Reboot-Time "09:00";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
EOF
systemctl enable --now --quiet unattended-upgrades

paso "fail2ban para SSH"
cat >/etc/fail2ban/jail.d/vortex.local <<'EOF'
[sshd]
enabled = true
backend = systemd
maxretry = 5
findtime = 10m
bantime = 1h
EOF
systemctl enable --quiet fail2ban
systemctl restart fail2ban

paso "ufw: solo SSH"
# Docker no publica ningún puerto hacia afuera (compose.yml), así que ufw y Docker no
# se pisan. Contabo no tiene firewall de red delante: ufw es la barrera del host.
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow OpenSSH >/dev/null
ufw --force enable >/dev/null

paso "Vortex en /opt/vortex"
install -d -m 750 -o despliegue -g despliegue /opt/vortex /var/lib/vortex
install -d -m 700 -o despliegue -g despliegue /var/lib/vortex/respaldo
if [[ ! -d /opt/vortex/repo/.git ]]; then
	sudo -u despliegue git clone --quiet "$REPO_URL" /opt/vortex/repo
fi
sudo -u despliegue git -C /opt/vortex/repo fetch --quiet origin main
# De root: la llave de despliegue no puede cambiar lo que ella misma corre.
install -m 755 -o root -g root /opt/vortex/repo/infra/vps/scripts/desplegar.sh /usr/local/sbin/vortex-desplegar
cat >/usr/local/bin/vortex <<'EOF'
#!/usr/bin/env bash
# docker compose del stack de Vortex con su .env y su versión (ADR-020):
#   vortex ps · vortex logs -f auth · vortex --profile admin up -d studio
# Corre como `despliegue`, el dueño del .env.
if [[ $(id -un) != despliegue ]]; then
	exec sudo -u despliegue "$0" "$@"
fi
source /opt/vortex/repo/infra/vps/scripts/comun.sh
cd /opt/vortex
compose "$@"
EOF
chmod 755 /usr/local/bin/vortex

paso "respaldo nocturno (08:00 UTC)"
install -m 644 /opt/vortex/repo/infra/vps/systemd/vortex-respaldo.service \
	/opt/vortex/repo/infra/vps/systemd/vortex-respaldo.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now --quiet vortex-respaldo.timer

paso ".env de /opt/vortex"
if [[ ! -f /opt/vortex/.env ]]; then
	sudo -u despliegue python3 /opt/vortex/repo/infra/vps/scripts/generar_secretos.py /opt/vortex/.env
else
	echo "ya existe: no se toca"
fi

cat <<EOF

Listo. Antes de cerrar esta sesión, en otra terminal:
  ssh $ADMIN@<ip>          (root ya no puede entrar)
Después, siguiendo el runbook:
  1. Llenar lo que falta:  sudo nano /opt/vortex/.env
     y comprobar:          sudo -u despliegue python3 /opt/vortex/repo/infra/vps/scripts/generar_secretos.py --verificar /opt/vortex/.env
  2. Guardar RESTIC_PASSWORD en el gestor de contraseñas.
  3. ANON_KEY para GitHub: sudo -u despliegue python3 /opt/vortex/repo/infra/vps/scripts/generar_secretos.py --clave-publica /opt/vortex/.env
  4. Correr el workflow "Deploy VPS (Contabo)".
EOF
