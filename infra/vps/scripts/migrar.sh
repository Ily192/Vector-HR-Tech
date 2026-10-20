#!/usr/bin/env bash
# Aplica las migraciones de infra/supabase/migrations que falten, en orden (ADR-020).
#
# Cada una va en su transacción y queda anotada en supabase_migrations.schema_migrations,
# la tabla del CLI de Supabase (`supabase db push` y `supabase migration list` la leen
# igual). Corre como `postgres`, el dueño del esquema, como el CLI. Necesita Auth y
# Storage arriba: crean `auth.users` y `storage.buckets` al arrancar, y las migraciones
# los usan (scripts/levantar.sh las corre en ese orden).
set -Eeuo pipefail
# shellcheck source=comun.sh
source "$(dirname "${BASH_SOURCE[0]}")/comun.sh"

sql() {
	compose exec -T -e PGOPTIONS="-c client_min_messages=warning" db \
		psql -h 127.0.0.1 -U postgres -d postgres -v ON_ERROR_STOP=1 -q "$@"
}

sql -c "create schema if not exists supabase_migrations;
	create table if not exists supabase_migrations.schema_migrations
		(version text not null primary key, statements text[], name text);"
aplicadas=$(sql -tA -c "select version from supabase_migrations.schema_migrations")

nuevas=0
for archivo in "$VORTEX_REPO"/infra/supabase/migrations/*.sql; do
	base=$(basename "$archivo" .sql)
	if [[ ! $base =~ ^([0-9]+)_([a-z0-9_]+)$ ]]; then
		log "nombre de migración inválido: $base"
		exit 1
	fi
	version=${BASH_REMATCH[1]}
	nombre=${BASH_REMATCH[2]}
	if grep -qx "$version" <<<"$aplicadas"; then
		continue
	fi
	log "migración $base"
	anotar=$(printf "insert into supabase_migrations.schema_migrations (version, name) values ('%s', '%s');" \
		"$version" "$nombre")
	# La anotación entra en la misma transacción que la migración. Si el archivo trae su
	# propio begin/commit, va antes de su último commit; si no, psql envuelve todo en una.
	if grep -qiE '^[[:space:]]*commit[[:space:]]*;[[:space:]]*$' "$archivo"; then
		awk -v anotar="$anotar" '
			{ lineas[NR] = $0 }
			tolower($0) ~ /^[[:space:]]*commit[[:space:]]*;[[:space:]]*$/ { ultimo = NR }
			END { for (i = 1; i <= NR; i++) { if (i == ultimo) print anotar; print lineas[i] } }
		' "$archivo" | sql -f -
	else
		{
			cat "$archivo"
			printf '\n%s\n' "$anotar"
		} | sql --single-transaction -f -
	fi
	nuevas=$((nuevas + 1))
done

# PostgREST recarga su caché del esquema (sin esto no ve las funciones nuevas).
sql -c "notify pgrst, 'reload schema';"
log "migraciones al día ($nuevas nuevas)"
