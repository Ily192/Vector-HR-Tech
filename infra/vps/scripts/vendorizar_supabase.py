"""Trae a `infra/vps/supabase/` la configuración del Supabase autoalojado oficial.

    python3 infra/vps/scripts/vendorizar_supabase.py <commit de supabase/supabase>

Baja de `supabase/supabase@<commit>/docker` el gateway (Envoy) y los SQL de arranque
de la base, y les quita lo que este stack no corre:

- del gateway, las rutas y los clusters de Realtime, Edge Functions, postgres-meta y
  Studio. Studio y meta solo se levantan con el perfil `admin` y se entra a Studio por
  un túnel SSH, nunca por el gateway (ADR-020);
- de la base, nada: `webhooks.sql`, `roles.sql` y `jwt.sql` quedan tal cual (el primero
  crea `supabase_functions_admin`, al que `roles.sql` le pone contraseña).

También saca el `pg_hba.conf` de la imagen de la base que fija `compose.yml` y le añade
la conexión de réplica por el socket local que usa el respaldo físico
(`pg_basebackup`, scripts/respaldar.sh).

Se corre al actualizar versiones (runbook, "Actualizar Supabase") y el resultado se
revisa en el diff del PR. Necesita red y Docker.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "supabase"
COMPOSE = RAIZ / "compose.yml"

QUITAR = ("realtime", "functions", "meta", "studio")
REPLICA = """
# Vortex (ADR-020): el respaldo físico (`pg_basebackup`, infra/vps/scripts/respaldar.sh)
# entra por el socket local como supabase_admin, igual que la línea `local all` de arriba.
local replication  supabase_admin     trust
"""


def bajar(commit: str, ruta: str) -> str:
    url = f"https://raw.githubusercontent.com/supabase/supabase/{commit}/docker/{ruta}"
    for intento in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as respuesta:
                return respuesta.read().decode("utf-8")
        except OSError:
            if intento == 2:
                raise
    raise AssertionError("inalcanzable")


def bloques(lineas: list[str], inicio: re.Pattern[str]) -> list[tuple[int, int]]:
    """Rangos [a, b) de los elementos de una lista YAML que empiezan con `inicio`."""
    marcas = [i for i, linea in enumerate(lineas) if inicio.match(linea)]
    if not marcas:
        raise SystemExit(f"no encontré elementos con {inicio.pattern!r}")
    sangria = len(lineas[marcas[0]]) - len(lineas[marcas[0]].lstrip())
    rangos = []
    for a in marcas:
        b = a + 1
        while b < len(lineas):
            linea = lineas[b]
            texto = linea.strip()
            if texto and len(linea) - len(linea.lstrip()) < sangria:
                break
            if b in marcas:
                break
            b += 1
        rangos.append((a, b))
    return rangos


def sin_elementos(texto: str, inicio: str, quitar: re.Pattern[str]) -> tuple[str, int]:
    lineas = texto.splitlines(keepends=True)
    fuera = [r for r in bloques(lineas, re.compile(inicio)) if quitar.search("".join(lineas[r[0] : r[1]]))]
    for a, b in reversed(fuera):
        del lineas[a:b]
    return "".join(lineas), len(fuera)


def cabecera(commit: str, ruta: str, comentario: str, nota: str) -> str:
    return (
        f"{comentario} Vendorizado de supabase/supabase@{commit[:12]}, docker/{ruta},\n"
        f"{comentario} con infra/vps/scripts/vendorizar_supabase.py. {nota}\n"
        f"{comentario} No editar a mano: se regenera al actualizar Supabase.\n"
    )


def con_cabecera(contenido: str, encabezado: str) -> str:
    if contenido.startswith("#!"):
        primera, _, resto = contenido.partition("\n")
        return f"{primera}\n{encabezado}{resto}"
    return encabezado + contenido


def imagen_de_la_base() -> str:
    coincidencia = re.search(r"^\s*image:\s*(\S*supabase/postgres:\S+)", COMPOSE.read_text("utf-8"), re.M)
    if not coincidencia:
        raise SystemExit("no encontré la imagen de la base en compose.yml")
    return coincidencia.group(1)


def escribir(ruta: pathlib.Path, contenido: str) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(contenido.replace("\r\n", "\n").encode("utf-8"))
    print(f"  {ruta.relative_to(RAIZ.parents[1])}")


def main() -> None:
    if len(sys.argv) != 2 or not re.fullmatch(r"[0-9a-f]{40}", sys.argv[1]):
        raise SystemExit("uso: vendorizar_supabase.py <commit de 40 caracteres de supabase/supabase>")
    commit = sys.argv[1]
    servicios = re.compile(r"cluster:\s*(" + "|".join(QUITAR) + r")\s*$", re.M)
    nota = "Sin " + ", ".join(QUITAR) + "."

    cds, n_clusters = sin_elementos(
        bajar(commit, "volumes/api/envoy/cds.yaml"),
        r"^  - '@type'",
        re.compile(r"^    name:\s*(" + "|".join(QUITAR) + r")\s*$", re.M),
    )
    lds, n_rutas = sin_elementos(
        bajar(commit, "volumes/api/envoy/lds.template.yaml"),
        r"^ {22}- (match:|name: )",
        servicios,
    )
    if servicios.search(lds):
        raise SystemExit("quedó una ruta hacia un cluster quitado")
    print(f"Gateway: quité {n_clusters} clusters y {n_rutas} rutas ({', '.join(QUITAR)}).")

    api = DESTINO / "api"
    escribir(api / "cds.yaml", con_cabecera(cds, cabecera(commit, "volumes/api/envoy/cds.yaml", "#", nota)))
    escribir(
        api / "lds.template.yaml",
        con_cabecera(lds, cabecera(commit, "volumes/api/envoy/lds.template.yaml", "#", nota)),
    )
    for archivo in ("envoy.yaml", "docker-entrypoint.sh"):
        ruta = f"volumes/api/envoy/{archivo}"
        escribir(api / archivo, con_cabecera(bajar(commit, ruta), cabecera(commit, ruta, "#", "Sin cambios.")))
    for archivo in ("webhooks.sql", "roles.sql", "jwt.sql"):
        ruta = f"volumes/db/{archivo}"
        escribir(
            DESTINO / "db" / archivo,
            con_cabecera(bajar(commit, ruta), cabecera(commit, ruta, "--", "Sin cambios.")),
        )

    imagen = imagen_de_la_base()
    hba = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "cat", imagen, "/etc/postgresql/pg_hba.conf"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    escribir(
        DESTINO / "db" / "pg_hba.conf",
        f"# Sacado de {imagen} (/etc/postgresql/pg_hba.conf) con\n"
        "# infra/vps/scripts/vendorizar_supabase.py; solo se le añade la línea del final.\n"
        + hba.rstrip("\n")
        + "\n"
        + REPLICA,
    )


if __name__ == "__main__":
    main()
