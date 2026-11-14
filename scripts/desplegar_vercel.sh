#!/usr/bin/env bash
# Despliega en producción, en el equipo de Vercel de Andres, una copia LIMPIA de main.
#
# Sube solo los archivos versionados en git (`git archive`), desde una carpeta temporal
# fuera del repo. La CLI de Vercel no respeta el .gitignore: el 2026-11-12 subió
# var-local.env y .env desde el repo. Aquí nunca ve var-local.*, .env ni .claude/.
#
# Uso, desde la raíz del repo:  bash scripts/desplegar_vercel.sh panel|empleos
#
# Requisitos: la CLI de Vercel y, en var-local.env (no versionado), VERCEL_TOKEN_ANDRES,
# VERCEL_EQUIPO_ANDRES, VERCEL_PROYECTO_PANEL y VERCEL_PROYECTO_EMPLEOS. Los IDs no son
# secretos, pero el repo es público y no los publica. El token pasa a la CLI por variable
# de entorno; nunca se escribe ni se imprime.
set -euo pipefail

REPO="$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)"
leer() { grep -m1 "^$1=" "$REPO/var-local.env" | cut -d= -f2- | tr -d '\r' || true; }
case "${1:-}" in
  panel)   PROYECTO="$(leer VERCEL_PROYECTO_PANEL)" ;;
  empleos) PROYECTO="$(leer VERCEL_PROYECTO_EMPLEOS)" ;;
  *) echo "uso: $0 panel|empleos" >&2; exit 2 ;;
esac
EQUIPO="$(leer VERCEL_EQUIPO_ANDRES)"
if [ -z "$PROYECTO" ] || [ -z "$EQUIPO" ]; then
  echo "faltan VERCEL_EQUIPO_ANDRES o el proyecto de $1 en var-local.env" >&2
  exit 1
fi

# Candado 1: se despliega lo que está en GitHub, no un main local con commits sin subir.
git -C "$REPO" fetch -q origin main
if [ "$(git -C "$REPO" rev-parse main)" != "$(git -C "$REPO" rev-parse origin/main)" ]; then
  echo "ABORTADO: main local y origin/main no coinciden. Haz pull o push antes." >&2
  exit 1
fi

DESTINO="$(mktemp -d "${TMPDIR:-/tmp}/fluveai-despliegue-$1.XXXXXX")"
trap 'cd / && rm -rf "$DESTINO"' EXIT
git -C "$REPO" archive --format=tar main | tar -x -C "$DESTINO"

# Candado 2: si la copia trae algo con claves, no se despliega.
if find "$DESTINO" \( -name 'var-local*' -o -name '.env' -o \( -name '.env.*' -a ! -name '.env.example' \) \
     -o -name '*.pem' -o -name '*_ed25519' -o -path '*/.claude/worktrees*' -o -name 'settings.local.json' \) \
     | grep -q .; then
  echo "ABORTADO: la copia trae archivos sensibles" >&2
  exit 1
fi
echo "copia limpia de main ($(git -C "$REPO" rev-parse --short main)): $(find "$DESTINO" -type f | wc -l) archivos → $1"

VERCEL_TOKEN="$(leer VERCEL_TOKEN_ANDRES)"
[ -n "$VERCEL_TOKEN" ] || { echo "falta VERCEL_TOKEN_ANDRES en var-local.env" >&2; exit 1; }
export VERCEL_TOKEN VERCEL_ORG_ID="$EQUIPO" VERCEL_PROJECT_ID="$PROYECTO"

cd "$DESTINO"
vercel deploy --prod --yes
