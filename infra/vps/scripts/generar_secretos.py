"""Crea o completa el .env del VPS sin mostrar ningún secreto (ADR-020).

    python3 generar_secretos.py /opt/vortex/.env                 # crear o completar
    python3 generar_secretos.py --verificar /opt/vortex/.env     # ¿falta algo?
    python3 generar_secretos.py --clave-publica /opt/vortex/.env # ANON_KEY

Parte de `infra/vps/.env.example`. Conserva todo valor que ya tenga el archivo, así que
correrlo dos veces no cambia nada, y genera los que la plantilla deja vacíos en la
sección "Generados": contraseñas y secretos aleatorios, y las claves `anon` y
`service_role` firmadas con JWT_SECRET (las mismas que da utils/generate-keys.sh del
Supabase autoalojado). Escribe con permisos 600 y al final dice qué generó y qué falta
llenar a mano, nunca los valores.

`--verificar` sale con error si falta un valor obligatorio o si las claves no están
firmadas con JWT_SECRET; lo corre scripts/levantar.sh antes de tocar nada.
`--clave-publica` imprime solo ANON_KEY, que es pública por diseño (la lleva el panel
en el navegador) y va en la variable SUPABASE_ANON_KEY de GitHub.

Solo usa la biblioteca estándar: corre con el python3 de Ubuntu.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import pathlib
import re
import secrets
import sys
import tempfile
import time

PLANTILLA = pathlib.Path(__file__).resolve().parents[1] / ".env.example"
LINEA = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")

#: Cinco años, como utils/generate-keys.sh.
VIGENCIA_DE_LAS_CLAVES_S = 5 * 365 * 24 * 3600


def _hex(n: int):
    return lambda: secrets.token_hex(n)


#: Lo que se genera si está vacío. Solo letras y números: la contraseña de Postgres va
#: dentro de URLs de conexión, y la de Redis también.
GENERADOS = {
    "POSTGRES_PASSWORD": _hex(16),
    "JWT_SECRET": _hex(32),
    "DASHBOARD_PASSWORD": _hex(16),
    "PG_META_CRYPTO_KEY": _hex(24),
    "REDIS_PASSWORD": _hex(24),
    "HR_ENGINE_JWT_SECRET": _hex(32),
    "RESTIC_PASSWORD": _hex(32),
}
CLAVES = {"ANON_KEY": "anon", "SERVICE_ROLE_KEY": "service_role"}

#: Lo que se llena a mano y sin lo cual el stack no sirve en producción.
OBLIGATORIOS = (
    "DOMINIO_EMPLEOS",
    "DOMINIO_PANEL",
    "DOMINIO_API",
    "DOMINIO_DIAGNOSTICO",
    "SMTP_ADMIN_EMAIL",
    "SMTP_SENDER_NAME",
    "ASUNTO_INVITACION",
    "ASUNTO_ENLACE_MAGICO",
    "RESTIC_REPOSITORY",
)
#: Obligatorios solo si se sale a internet (en la prueba local no hay túnel ni Resend).
DE_PRODUCCION = ("SMTP_PASS", "CLOUDFLARE_TUNNEL_TOKEN", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")


def _b64url(datos: bytes) -> str:
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode()


def firmar(rol: str, secreto: str, ahora: int | None = None) -> str:
    """JWT HS256 con los claims de utils/generate-keys.sh: role, iss, iat y exp."""
    iat = int(time.time()) if ahora is None else ahora
    cabecera = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    cuerpo = _b64url(
        json.dumps(
            {"role": rol, "iss": "supabase", "iat": iat, "exp": iat + VIGENCIA_DE_LAS_CLAVES_S},
            separators=(",", ":"),
        ).encode()
    )
    firma = hmac.new(secreto.encode(), f"{cabecera}.{cuerpo}".encode(), hashlib.sha256).digest()
    return f"{cabecera}.{cuerpo}.{_b64url(firma)}"


def rol_si_es_valida(clave: str, secreto: str) -> str | None:
    """El `role` de la clave si la firmó `secreto`; None si no."""
    partes = clave.split(".")
    if len(partes) != 3:
        return None
    esperada = hmac.new(
        secreto.encode(), f"{partes[0]}.{partes[1]}".encode(), hashlib.sha256
    ).digest()
    if not hmac.compare_digest(_b64url(esperada), partes[2]):
        return None
    cuerpo = json.loads(base64.urlsafe_b64decode(partes[1] + "=" * (-len(partes[1]) % 4)))
    return cuerpo.get("role")


def leer(ruta: pathlib.Path) -> dict[str, str]:
    valores: dict[str, str] = {}
    if ruta.exists():
        for linea in ruta.read_text("utf-8").splitlines():
            coincidencia = LINEA.match(linea.strip())
            if coincidencia:
                valores[coincidencia.group(1)] = coincidencia.group(2)
    return valores


def completar(actuales: dict[str, str]) -> tuple[list[str], dict[str, str], list[str]]:
    """Las líneas del archivo nuevo, los valores finales y los nombres generados."""
    plantilla = PLANTILLA.read_text("utf-8").splitlines()
    valores = dict(actuales)
    generados: list[str] = []
    for linea in plantilla:
        coincidencia = LINEA.match(linea)
        if not coincidencia:
            continue
        nombre, por_omision = coincidencia.groups()
        if valores.get(nombre):
            continue
        if nombre in GENERADOS:
            valores[nombre] = GENERADOS[nombre]()
            generados.append(nombre)
        elif nombre not in CLAVES:
            valores[nombre] = por_omision

    secreto = valores["JWT_SECRET"]
    for nombre, rol in CLAVES.items():
        if "JWT_SECRET" in generados or not valores.get(nombre):
            valores[nombre] = firmar(rol, secreto)
            generados.append(nombre)

    salida = []
    de_la_plantilla = set()
    for linea in plantilla:
        coincidencia = LINEA.match(linea)
        if coincidencia:
            de_la_plantilla.add(coincidencia.group(1))
        salida.append(
            f"{coincidencia.group(1)}={valores[coincidencia.group(1)]}" if coincidencia else linea
        )
    extra = [n for n in actuales if n not in de_la_plantilla]
    if extra:
        salida += ["", "# ─── Sin plantilla (se conservan) ───"] + [
            f"{n}={actuales[n]}" for n in extra
        ]
    return salida, valores, generados


def problemas(valores: dict[str, str], produccion: bool) -> list[str]:
    faltan = [n for n in OBLIGATORIOS + (DE_PRODUCCION if produccion else ()) if not valores.get(n)]
    lista = [f"falta {n}" for n in faltan]
    lista += [f"falta {n}" for n in (*GENERADOS, *CLAVES) if not valores.get(n)]
    secreto = valores.get("JWT_SECRET", "")
    for nombre, rol in CLAVES.items():
        if valores.get(nombre) and secreto and rol_si_es_valida(valores[nombre], secreto) != rol:
            lista.append(f"{nombre} no está firmada con JWT_SECRET para el rol {rol}")
    for nombre in ("DOMINIO_EMPLEOS", "DOMINIO_PANEL", "DOMINIO_API", "DOMINIO_DIAGNOSTICO"):
        # Con puerto solo en la prueba local (localhost:8080).
        if valores.get(nombre) and not re.fullmatch(r"[a-z0-9.-]+(:[0-9]{2,5})?", valores[nombre]):
            lista.append(f"{nombre} tiene que ser solo el dominio, sin https:// ni barras")
    return lista


def escribir(ruta: pathlib.Path, lineas: list[str]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=".env.")
    try:
        os.chmod(temporal, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
            archivo.write("\n".join(lineas) + "\n")
        os.replace(temporal, ruta)
    finally:
        if os.path.exists(temporal):
            os.unlink(temporal)
    os.chmod(ruta, 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("env", type=pathlib.Path, help="ruta del .env del servidor")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--verificar", action="store_true", help="no escribe; falla si falta algo")
    grupo.add_argument("--clave-publica", action="store_true", help="imprime solo ANON_KEY")
    parser.add_argument(
        "--local", action="store_true", help="para la prueba local: sin túnel, Resend ni R2"
    )
    args = parser.parse_args()

    actuales = leer(args.env)
    if args.clave_publica:
        if not actuales.get("ANON_KEY"):
            print("todavía no hay ANON_KEY: corre primero sin opciones", file=sys.stderr)
            return 1
        print(actuales["ANON_KEY"])
        return 0
    if args.verificar:
        lista = problemas(actuales, produccion=not args.local)
        for problema in lista:
            print(f"{args.env}: {problema}", file=sys.stderr)
        return 1 if lista else 0

    lineas, valores, generados = completar(actuales)
    escribir(args.env, lineas)
    print(f"{args.env} listo (600).")
    if generados:
        print("Generados: " + ", ".join(generados) + ".")
    pendientes = [p for p in problemas(valores, produccion=not args.local) if p.startswith("falta")]
    if pendientes:
        print("Por llenar a mano: " + ", ".join(p.removeprefix("falta ") for p in pendientes) + ".")
    if "RESTIC_PASSWORD" in generados:
        print("Copia RESTIC_PASSWORD a tu gestor de contraseñas: sin ella no se restaura nada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
