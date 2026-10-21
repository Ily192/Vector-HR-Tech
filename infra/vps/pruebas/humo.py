"""Lo que el e2e del plan gratis no ve del stack del VPS (pruebas/probar_en_local.sh).

    python humo.py <.env de prueba> borde
    python humo.py <.env de prueba> diagnostico
    python humo.py <.env de prueba> foto <estado.json>
    python humo.py <.env de prueba> comparar <estado.json>

- `borde`: lo que Caddy y el gateway no tienen que dejar pasar:
  - Studio y el resto del gateway no se publican;
  - sin apikey no se entra;
  - sin invitación no hay alta;
  - un correo desconocido no recibe enlace, y una cuenta invitada que aún no entra sí;
  - el panel es una SPA con caché larga en sus assets;
  - Auth usa las plantillas en español, que sirve Caddy (la del enlace mágico, en
    Mailpit).
- `diagnostico`: el diagnóstico gratuito (migración 0017):
  - la SPA con su CSP, y /api/diagnostico solo con POST;
  - registra por /api/diagnostico, que Caddy reenvía a la RPC con la clave pública;
  - anon no lee la tabla, ni por la API ni pidiendo el esquema `privado`;
  - lo inválido es 400 y el cuarto del mismo correo en una hora, 429;
  - el aviso llega a Mailpit (el beat del stack, cada minuto).
- `foto` y `comparar`: lo que tiene que volver igual después de restaurar el respaldo.
  Son los conteos de empresas, cuentas, vacantes, aplicaciones y CVs, y un CV byte a
  byte.

El flujo completo (alta, invitación, vacante, aplicaciones, worker, .zip) lo recorre
`pnpm e2e:flujo` con E2E_REMOTO=1 (packages/e2e). Necesita httpx: se corre con el
entorno del hr-engine (`python -m uv run`).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
import time
import uuid
from datetime import datetime

import httpx

# La consola de Windows no es UTF-8 por defecto (los ✓ de la salida).
sys.stdout.reconfigure(encoding="utf-8")

MAILPIT = "http://127.0.0.1:8025"
IP_DE_PRUEBA = "203.0.113.7"  # TEST-NET-3: hace de CF-Connecting-IP

env = {}
for linea in pathlib.Path(sys.argv[1]).read_text("utf-8").splitlines():
    if "=" in linea and not linea.startswith("#"):
        clave, _, valor = linea.partition("=")
        env[clave] = valor

ANON, SERVICIO = env["ANON_KEY"], env["SERVICE_ROLE_KEY"]
API = f"http://{env['DOMINIO_API']}"
PANEL = f"http://{env['DOMINIO_PANEL']}"
DIAGNOSTICO = f"http://{env['DOMINIO_DIAGNOSTICO']}"
http = httpx.Client(timeout=30, headers={"CF-Connecting-IP": IP_DE_PRUEBA})
servicio = {"apikey": SERVICIO, "Authorization": f"Bearer {SERVICIO}"}


def ok(condicion: bool, paso: str, detalle: object = "") -> None:
    if not condicion:
        print(f"✗ {paso} {detalle}")
        sys.exit(1)
    print(f"✓ {paso}")


def borde() -> None:
    r = http.get(f"{PANEL}/")
    ok(r.status_code == 200 and 'id="root"' in r.text, "panel servido por Caddy")
    entrada = re.search(r'/assets/entrada-[^"]+\.js', r.text)
    r = http.get(f"{PANEL}{entrada.group(0) if entrada else '/assets/x.js'}")
    ok(
        r.status_code == 200 and "immutable" in r.headers.get("cache-control", ""),
        "assets del panel con caché larga",
    )
    r = http.get(f"{PANEL}/vacantes/una-ruta-de-la-spa")
    ok(r.status_code == 200 and 'id="root"' in r.text, "las rutas de la SPA caen en index.html")
    r = http.get(f"{API}/salud/hr-engine")
    ok(r.status_code == 200 and r.text == "ok", "/salud/hr-engine para el monitoreo")
    for ruta in ("/", "/pg/tables", "/functions/v1/x", "/realtime/v1/api"):
        ok(
            http.get(f"{API}{ruta}").status_code == 404,
            f"{ruta} no se publica (Studio y el resto del gateway)",
        )
    r = http.get(f"{API}/rest/v1/vacantes_publicas")
    ok(r.status_code == 401, "sin apikey el gateway responde 401", r.status_code)
    r = http.get(f"{API}/rest/v1/", headers={"apikey": ""})
    ok(r.status_code == 401, "con apikey vacía tampoco hay esquema", r.status_code)
    intruso = f"intruso-{uuid.uuid4().hex[:6]}@x.test"
    r = http.post(
        f"{API}/auth/v1/signup",
        headers={"apikey": ANON},
        json={"email": intruso, "password": uuid.uuid4().hex},
    )
    ok(r.status_code >= 400, "sin invitación no hay alta (trigger handle_new_user)", r.status_code)
    r = http.post(
        f"{API}/auth/v1/otp",
        headers={"apikey": ANON},
        json={"email": intruso, "create_user": False},
    )
    ok(r.status_code == 422, "y no quedó una cuenta a medias", r.text[:120])
    r = http.post(
        f"{API}/auth/v1/otp",
        headers={"apikey": ANON},
        json={"email": f"nadie-{uuid.uuid4().hex[:6]}@x.test", "create_user": False},
    )
    ok(r.status_code == 422, "un correo desconocido no recibe enlace", r.text[:120])


def plantilla(correo: str) -> None:
    """El enlace mágico de una cuenta que existe sale con la plantilla de Caddy."""
    for _ in range(4):
        enviado = time.time()
        r = http.post(
            f"{API}/auth/v1/otp",
            headers={"apikey": ANON},
            json={"email": correo, "create_user": False},
        )
        if r.status_code != 429:
            break
        print("  (Auth pide esperar entre correos a la misma cuenta: 60 s, como en producción)")
        time.sleep(31)
    ok(r.status_code == 200, "Auth manda el enlace mágico por SMTP", r.text[:200])
    limite = time.time() + 60
    while time.time() < limite:
        lista = httpx.get(
            f"{MAILPIT}/api/v1/search", params={"query": f'to:"{correo}"'}, timeout=10
        ).json()
        for mensaje in lista.get("messages", []):
            llegado = datetime.fromisoformat(mensaje["Created"].replace("Z", "+00:00")).timestamp()
            if mensaje["Subject"] == env["ASUNTO_ENLACE_MAGICO"] and llegado >= enviado - 2:
                cuerpo = httpx.get(f"{MAILPIT}/api/v1/message/{mensaje['ID']}", timeout=10).json()
                # El botón de infra/supabase/templates; la plantilla de Auth es en inglés.
                ok(
                    "Entrar al panel" in cuerpo["HTML"]
                    and f"{API}/auth/v1/verify" in cuerpo["HTML"],
                    "con la plantilla en español y el enlace a la API pública",
                )
                return
        time.sleep(1)
    ok(False, f"llega el enlace mágico a {correo}")


def diagnostico() -> None:
    r = http.get(f"{DIAGNOSTICO}/")
    ok(r.status_code == 200 and 'id="root"' in r.text, "diagnóstico servido por Caddy")
    csp = r.headers.get("content-security-policy", "")
    ok(
        "connect-src 'self' https://challenges.cloudflare.com" in csp,
        "con CSP: solo conecta con su dominio y Turnstile",
        csp,
    )
    r = http.get(f"{DIAGNOSTICO}/una-ruta-de-la-spa")
    ok(r.status_code == 200 and 'id="root"' in r.text, "las rutas de la SPA caen en index.html")
    r = http.get(f"{DIAGNOSTICO}/api/diagnostico")
    ok(r.status_code == 405, "/api/diagnostico solo acepta POST", r.status_code)

    marca = f"Humo {uuid.uuid4().hex[:8]}"
    correo = f"prospecto-{uuid.uuid4().hex[:8]}@humo.test"

    def registrar(**cambios: object) -> httpx.Response:
        cuerpo = {
            "p_nombre": "Mariana Ruiz",
            "p_empresa": marca,
            "p_correo": correo,
            "p_origen": "linkedin",
            "p_utm_medium": "cpc",
            "p_utm_campaign": "humo",
            "p_respuestas": {"p1": "a"},
            "p_resultado": {
                "version": 1,
                "procesos": [
                    {
                        "id": "nomina",
                        "nombre": "Nómina",
                        "horasSemana": 12,
                        "etapa": "Automatizar",
                        "horasRecuperablesMes": 31.2,
                    }
                ],
                "horasRecuperablesMes": 31.2,
                "horasRecuperablesAnio": 374.4,
            },
            "p_horas_recuperables_mes": 31.2,
            "p_turnstile_token": None,
            "p_sin_fines_comerciales": True,
            **cambios,
        }
        # Una IP por petición: el freno por IP (5 en una hora) no entra en esta prueba.
        ip = f"198.51.100.{uuid.uuid4().int % 250 + 1}"
        return http.post(
            f"{DIAGNOSTICO}/api/diagnostico", json=cuerpo, headers={"CF-Connecting-IP": ip}
        )

    enviado = time.time()
    r = registrar()
    ok(r.status_code in (200, 204), "anon registra un diagnóstico por /api/diagnostico", r.text)
    r = registrar(p_correo="no-es-un-correo")
    ok(r.status_code == 400, "un diagnóstico inválido es 400", (r.status_code, r.text[:120]))
    for _ in range(2):
        registrar()
    r = registrar()
    ok(r.status_code == 429, "el cuarto del mismo correo en una hora es 429", r.status_code)

    anon = {"apikey": ANON, "Authorization": f"Bearer {ANON}"}
    r = http.get(f"{API}/rest/v1/diagnosticos", headers=anon)
    ok(r.status_code >= 400 and marca not in r.text, "anon no lee los diagnósticos", r.status_code)
    r = http.get(f"{API}/rest/v1/diagnosticos", headers={**anon, "Accept-Profile": "privado"})
    ok(
        r.status_code >= 400 and marca not in r.text,
        "ni pidiendo el esquema privado",
        r.status_code,
    )

    para = env.get("AVISO_DIAGNOSTICOS_PARA") or "hola@vectorhrtech.com"
    limite = time.time() + 150
    while time.time() < limite:
        lista = httpx.get(
            f"{MAILPIT}/api/v1/search", params={"query": f'to:"{para}"'}, timeout=10
        ).json()
        for mensaje in lista.get("messages", []):
            llegado = datetime.fromisoformat(mensaje["Created"].replace("Z", "+00:00")).timestamp()
            if llegado < enviado - 2:
                continue
            cuerpo = httpx.get(f"{MAILPIT}/api/v1/message/{mensaje['ID']}", timeout=10).json()
            if marca in cuerpo["Text"]:
                ok(
                    marca in mensaje["Subject"] or "diagnósticos" in mensaje["Subject"],
                    f"aviso con asunto seguro: {mensaje['Subject']}",
                )
                ok(
                    "1. Nómina (Automatizar): 31.2 h al mes" in cuerpo["Text"]
                    and "Contacto comercial: NO" in cuerpo["Text"],
                    f"el aviso llega a {para} con el top de procesos y la casilla de contacto",
                )
                return
        time.sleep(2)
    ok(False, f"llega el aviso del diagnóstico a {para}")


def contar(tabla: str) -> int:
    r = http.get(
        f"{API}/rest/v1/{tabla}",
        params={"select": "id"},
        headers={**servicio, "Prefer": "count=exact", "Range": "0-0"},
    )
    ok(r.status_code in (200, 206), f"contar {tabla}", r.text[:200])
    return int(r.headers["content-range"].split("/")[1])


def cvs() -> list[str]:
    """Las rutas de los CVs del bucket, carpeta por carpeta (una por empresa)."""

    def listar(prefijo: str) -> list[dict]:
        r = http.post(
            f"{API}/storage/v1/object/list/cvs",
            headers=servicio,
            json={"prefix": prefijo, "limit": 1000, "offset": 0},
        )
        ok(r.status_code == 200, f"listar cvs/{prefijo}", r.text[:200])
        return r.json()

    rutas = []
    for carpeta in listar(""):
        rutas += [f"{carpeta['name']}/{a['name']}" for a in listar(carpeta["name"]) if a.get("id")]
    return sorted(rutas)


def foto() -> dict:
    r = http.get(f"{API}/auth/v1/admin/users", params={"page": 1, "per_page": 1}, headers=servicio)
    ok(r.status_code == 200 and "x-total-count" in r.headers, "contar cuentas", r.text[:200])
    cuentas = int(r.headers["x-total-count"])
    rutas = cvs()
    ok(len(rutas) > 0, "hay CVs que comparar")
    cv = http.get(f"{API}/storage/v1/object/cvs/{rutas[0]}", headers=servicio)
    ok(cv.status_code == 200, "bajar un CV con la clave secreta")
    return {
        "cuentas": cuentas,
        "empresas": contar("empresas"),
        "vacantes": contar("vacantes"),
        "aplicaciones": contar("applications"),
        "cvs": len(rutas),
        "cv": rutas[0],
        "cv_sha256": hashlib.sha256(cv.content).hexdigest(),
    }


if __name__ == "__main__":
    modo = sys.argv[2]
    if modo == "borde":
        borde()
        plantilla(sys.argv[3])
    elif modo == "diagnostico":
        diagnostico()
    elif modo == "foto":
        estado = foto()
        pathlib.Path(sys.argv[3]).write_text(json.dumps(estado))
        print(f"  foto: {estado}")
    else:
        antes = json.loads(pathlib.Path(sys.argv[3]).read_text())
        despues = foto()
        for clave in ("cuentas", "empresas", "vacantes", "aplicaciones", "cvs", "cv", "cv_sha256"):
            ok(
                antes[clave] == despues[clave],
                f"{clave} igual que antes del respaldo",
                (antes[clave], despues[clave]),
            )
    print("\nTodo bien.")
