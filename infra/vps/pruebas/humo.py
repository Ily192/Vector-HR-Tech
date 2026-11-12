"""Lo que el e2e del plan gratis no ve del stack del VPS (pruebas/probar_en_local.sh).

    python humo.py <.env de prueba> borde <correo invitado>
    python humo.py <.env de prueba> alta
    python humo.py <.env de prueba> career-site
    python humo.py <.env de prueba> moderacion-preparar <estado.json>
    python humo.py <.env de prueba> moderacion-correo <estado.json>
    python humo.py <.env de prueba> foto <estado.json>
    python humo.py <.env de prueba> comparar <estado.json>

- `borde`: lo que Caddy y el gateway no tienen que dejar pasar:
  - Studio y el resto del gateway no se publican;
  - sin apikey no se entra;
  - sin invitación no hay alta;
  - un correo desconocido no recibe código, y una cuenta invitada que aún no entra sí;
  - Auth usa las plantillas en español, que sirve Caddy (la del código, en Mailpit), y
    el correo lleva el código y no un enlace.
- `alta`: `POST /alta/plan-gratis` por Caddy (ADR-017, enmienda del 2026-11-12): sin el
  secreto es 401; con datos que no sirven, 422; y pasado el tope por correo, 429 con
  Retry-After. El recorrido completo (código, panel, salir y volver) es del e2e.
- `career-site`: la clave del career site (rol `career_site`, migración 0017) contra el
  gateway y la Storage API de verdad: lee la vacante abierta y nada más, sube un CV, no
  lista ni baja ninguno, y borra solo el que nombra en `x-cv-ruta`. Necesita una
  vacante abierta: va después del e2e.
- `moderacion-preparar` y `moderacion-correo` (ADR-022): una vacante en revisión de una
  empresa sin verificar; entre los dos, probar_en_local.sh corre `moderacion.avisar` en
  el worker. Después: el resumen llega a hola@ (Mailpit) con el motivo y un enlace
  firmado; el enlace abre la página de revisión, "Aprobar" la publica, y la vacante
  aparece en `vacantes_publicas`.
- `foto` y `comparar`: lo que tiene que volver igual después de restaurar el respaldo.
  Son los conteos de empresas, cuentas, vacantes, aplicaciones y CVs, y un CV byte a
  byte.

El flujo completo (alta, invitación, vacante, aplicaciones, worker, .zip) lo recorre
`pnpm e2e:flujo` con E2E_REMOTO=1 (packages/e2e). El panel y el career site ya no son del
VPS (enmienda de ADR-020 del 2026-11-11): sus cabeceras y su caché son de Vercel
(vercel.json de cada app), así que aquí no se revisan. Necesita httpx: se corre con el
entorno del hr-engine (`python -m uv run`).
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sys
import time
import uuid
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

import httpx

# La consola de Windows no es UTF-8 por defecto (los ✓ de la salida).
sys.stdout.reconfigure(encoding="utf-8")

MAILPIT = os.environ.get("MAILPIT_URL", "http://127.0.0.1:8025")
IP_DE_PRUEBA = "203.0.113.7"  # TEST-NET-3: hace de CF-Connecting-IP

env = {}
for linea in pathlib.Path(sys.argv[1]).read_text("utf-8").splitlines():
    if "=" in linea and not linea.startswith("#"):
        clave, _, valor = linea.partition("=")
        env[clave] = valor

ANON, SERVICIO = env["ANON_KEY"], env["SERVICE_ROLE_KEY"]
API = f"http://{env['DOMINIO_API']}"
http = httpx.Client(timeout=30, headers={"CF-Connecting-IP": IP_DE_PRUEBA})
servicio = {"apikey": SERVICIO, "Authorization": f"Bearer {SERVICIO}"}


def ok(condicion: bool, paso: str, detalle: object = "") -> None:
    if not condicion:
        print(f"✗ {paso} {detalle}")
        sys.exit(1)
    print(f"✓ {paso}")


def borde() -> None:
    r = http.get(f"{API}/salud/hr-engine")
    ok(r.status_code == 200 and r.text == "ok", "/salud/hr-engine para el monitoreo")
    ok(
        r.headers.get("referrer-policy") == "strict-origin-when-cross-origin",
        "Caddy pone Referrer-Policy por defecto donde el upstream no la manda",
        r.headers.get("referrer-policy"),
    )
    for ruta in ("/", "/pg/tables", "/functions/v1/x", "/realtime/v1/api"):
        ok(
            http.get(f"{API}{ruta}").status_code == 404,
            f"{ruta} no se publica (Studio y el resto del gateway)",
        )
    # La página de revisión de la moderación (ADR-022): llega al hr-engine, con su secreto
    # (503 si falta MODERACION_SECRETO) y sin enlace firmado no muestra nada.
    r = http.get(f"{API}/moderacion/revisar", params={"t": "falso"})
    ok(r.status_code == 403, "/moderacion/revisar sin enlace firmado responde 403", r.status_code)
    r = http.post(f"{API}/moderacion/revisar", content=b"x" * 20_000)
    ok(r.status_code == 413, "y Caddy corta un formulario de más de 16 KB", r.status_code)
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
    ok(r.status_code == 422, "un correo desconocido no recibe código", r.text[:120])


def plantilla(correo: str) -> None:
    """El código de una cuenta que existe sale con la plantilla de Caddy.

    La cuenta invitada que aún no entra está sin confirmar: Auth le reenvía el correo de
    confirmación (GOTRUE_MAILER_AUTOCONFIRM=false), que también lleva el código.
    """
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
    ok(r.status_code == 200, "Auth manda el código por SMTP", r.text[:200])
    limite = time.time() + 60
    while time.time() < limite:
        lista = httpx.get(
            f"{MAILPIT}/api/v1/search", params={"query": f'to:"{correo}"'}, timeout=10
        ).json()
        for mensaje in lista.get("messages", []):
            llegado = datetime.fromisoformat(mensaje["Created"].replace("Z", "+00:00")).timestamp()
            if mensaje["Subject"] == env["ASUNTO_CODIGO"] and llegado >= enviado - 2:
                cuerpo = httpx.get(f"{MAILPIT}/api/v1/message/{mensaje['ID']}", timeout=10).json()
                texto = re.sub(r"<[^>]*>", " ", cuerpo["HTML"])
                # El texto de infra/supabase/templates; la plantilla de Auth es en inglés.
                ok(
                    "Tu código para entrar" in texto and re.search(r"\b\d{6}\b", texto),
                    "con la plantilla en español y el código de 6 dígitos",
                )
                ok(
                    "/auth/v1/verify" not in cuerpo["HTML"],
                    "sin enlace que un filtro de correo pueda gastar",
                )
                return
        time.sleep(1)
    ok(False, f"llega el código a {correo}")


def alta() -> None:
    """El endpoint del alta desde la web, por Caddy: secreto, datos y tope por correo."""
    url = f"{API}/alta/plan-gratis"
    correo = f"alta-{uuid.uuid4().hex[:8]}@humo.test"
    registro = {
        "nombre": "Humo del alta",
        "correo": correo,
        "publica_para": "propia",
        "empresa": f"Humo del alta {uuid.uuid4().hex[:6]}",
        "cargo": None,
        "web_empresa": "https://humo.test",
        "linkedin": None,
        "verificacion": "dominio",
        "pais": "mx",
        "tamano": "1-15",
        "sector": "otro",
        "contrataciones_mes": "0",
        "puestos": [],
        "ip": "198.51.100.77",
    }
    secreto = {"Authorization": f"Bearer {env['ALTA_SECRETO']}"}
    r = http.post(url, json={**registro, "lead_id": "humo-0"})
    ok(r.status_code == 401, "sin el secreto, 401", r.status_code)
    r = http.post(
        url, json={**registro, "lead_id": "humo-0"}, headers={"Authorization": "Bearer x"}
    )
    ok(r.status_code == 401, "con otro secreto, 401", r.status_code)
    r = http.post(url, json={**registro, "lead_id": "humo-0", "pais": "co"}, headers=secreto)
    ok(r.status_code == 422, "un país que no es del formulario, 422", r.status_code)
    r = http.post(
        url, content=b"x" * 20_000, headers={**secreto, "Content-Type": "application/json"}
    )
    ok(r.status_code == 413, "un cuerpo de más de 16 KB no pasa de Caddy", r.status_code)

    marca = uuid.uuid4().hex[:6]
    for i in range(3):
        r = http.post(url, json={**registro, "lead_id": f"humo-{marca}-{i}"}, headers=secreto)
        ok(
            r.status_code == 200 and r.json()["estado"] == "codigo_enviado",
            f"registro {i + 1} de 3 en la hora con el mismo correo",
            r.text[:200],
        )
    ok(
        r.json()["verificar_url"].endswith(f"/verificar#correo={correo.replace('@', '%40')}"),
        "vuelve a /verificar con el correo en el fragmento",
        r.json()["verificar_url"],
    )
    r = http.post(url, json={**registro, "lead_id": f"humo-{marca}-3"}, headers=secreto)
    ok(
        r.status_code == 429 and int(r.headers.get("Retry-After", "0")) > 0,
        "el cuarto, 429 con Retry-After",
        (r.status_code, r.headers.get("Retry-After")),
    )
    r = http.post(url, json={**registro, "lead_id": f"humo-{marca}-0"}, headers=secreto)
    ok(r.status_code == 200, "un reintento de la web no gasta el tope", r.status_code)


def career_site() -> None:
    """Lo que puede y no puede la clave del career site (0017), por el gateway."""
    clave = env["CAREER_SITE_KEY"]
    # El gateway solo acepta la anon o la service_role como apikey; el rol va en el JWT.
    suya = {"apikey": ANON, "Authorization": f"Bearer {clave}"}
    r = http.get(f"{API}/rest/v1/vacantes", params={"select": "id"}, headers={"apikey": clave})
    ok(r.status_code == 401, "el gateway no acepta la clave del career site como apikey")

    # El e2e elimina su vacante al terminar: una abierta solo para esta prueba.
    r = http.get(f"{API}/rest/v1/empresas", params={"select": "id", "limit": "1"}, headers=servicio)
    ok(r.status_code == 200 and len(r.json()) == 1, "hay una empresa", r.text[:200])
    slug = f"humo-career-site-{uuid.uuid4().hex[:8]}"
    r = http.post(
        f"{API}/rest/v1/vacantes",
        headers={**servicio, "Prefer": "return=representation"},
        json={
            "empresa_id": r.json()[0]["id"],
            "slug": slug,
            "title": "Humo del career site",
            "jd": "Vacante de la prueba de la clave del career site.",
            "status": "open",
        },
    )
    ok(r.status_code == 201, "una vacante abierta para la prueba", r.text[:200])
    vacante = r.json()[0]
    try:
        _career_site_contra(suya, vacante)
    finally:
        http.patch(
            f"{API}/rest/v1/vacantes",
            params={"id": f"eq.{vacante['id']}"},
            headers=servicio,
            json={"status": "closed"},
        )


def _career_site_contra(suya: dict[str, str], vacante: dict) -> None:
    r = http.get(
        f"{API}/rest/v1/vacantes",
        params={"select": "id,empresa_id", "slug": f"eq.{vacante['slug']}", "status": "eq.open"},
        headers=suya,
    )
    ok(
        r.status_code == 200
        and r.json() == [{"id": vacante["id"], "empresa_id": vacante["empresa_id"]}],
        "lee el id y la empresa de la vacante abierta",
        r.text[:200],
    )
    empresa = vacante["empresa_id"]
    for tabla, columnas in (("vacantes", "icp_text"), ("applications", "id"), ("empresas", "id")):
        r = http.get(f"{API}/rest/v1/{tabla}", params={"select": columnas}, headers=suya)
        ok(r.status_code in (401, 403), f"no lee {tabla}.{columnas}", r.status_code)

    pdf = b"%PDF-1.4\n% humo del career site\n"
    ruta = f"{empresa}/{uuid.uuid4()}.pdf"
    subir = {**suya, "Content-Type": "application/pdf"}
    r = http.post(f"{API}/storage/v1/object/cvs/{ruta}", headers=subir, content=pdf)
    ok(r.status_code == 200, "sube un CV a la carpeta de la empresa", r.text[:200])
    ajena = f"{uuid.uuid4()}/{uuid.uuid4()}.pdf"
    r = http.post(f"{API}/storage/v1/object/cvs/{ajena}", headers=subir, content=pdf)
    ok(r.status_code >= 400, "no a la carpeta de una empresa sin vacantes abiertas", r.status_code)
    r = http.post(
        f"{API}/storage/v1/object/list/cvs",
        headers=suya,
        json={"prefix": empresa, "limit": 100, "offset": 0},
    )
    ok(r.status_code == 200 and r.json() == [], "no lista los CVs", r.text[:200])
    r = http.get(f"{API}/storage/v1/object/cvs/{ruta}", headers=suya)
    ok(r.status_code >= 400, "no baja ni el que acaba de subir", r.status_code)

    borrar = {"prefixes": [ruta]}
    r = http.request("DELETE", f"{API}/storage/v1/object/cvs", headers=suya, json=borrar)
    ok(r.status_code == 200 and r.json() == [], "sin x-cv-ruta no borra", r.text[:200])
    r = http.get(f"{API}/storage/v1/object/cvs/{ruta}", headers=servicio)
    ok(r.status_code == 200, "el CV sigue en el bucket", r.status_code)
    r = http.request(
        "DELETE", f"{API}/storage/v1/object/cvs", headers={**suya, "x-cv-ruta": ruta}, json=borrar
    )
    ok(
        r.status_code == 200 and len(r.json()) == 1,
        "con su ruta en x-cv-ruta lo borra",
        r.text[:200],
    )
    r = http.get(f"{API}/storage/v1/object/cvs/{ruta}", headers=servicio)
    ok(r.status_code >= 400, "y ya no está", r.status_code)


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


def moderacion_preparar(ruta: str) -> None:
    """Una vacante en revisión de una empresa sin verificar, como la deja el barrido."""
    marca = uuid.uuid4().hex[:8]
    con_fila = {**servicio, "Prefer": "return=representation"}
    r = http.post(
        f"{API}/rest/v1/empresas",
        headers=con_fila,
        json={"name": f"Revisión humo {marca}", "slug": f"revision-humo-{marca}"},
    )
    ok(r.status_code == 201, "una empresa sin verificar, con la clave secreta", r.text[:200])
    empresa = r.json()[0]["id"]
    titulo = f"Promotor de ventas {marca}"
    r = http.post(
        f"{API}/rest/v1/vacantes",
        headers=con_fila,
        json={
            "empresa_id": empresa,
            "slug": f"revision-humo-{marca}",
            "title": titulo,
            "jd": "Escríbenos por WhatsApp para más información.",
            "status": "open",
            "moderacion": "en_revision",
            "motivos_moderacion": [
                {
                    "regla": "contacto_externo",
                    "senal": "Manda a contactar por WhatsApp",
                    "gravedad": "media",
                    "cita": "WhatsApp",
                    "corregir": None,
                }
            ],
        },
    )
    ok(r.status_code == 201, "una vacante en revisión", r.text[:200])
    vacante = r.json()[0]["id"]
    r = http.get(
        f"{API}/rest/v1/vacantes_publicas",
        params={"id": f"eq.{vacante}", "select": "id"},
        headers={"apikey": ANON},
    )
    ok(r.status_code == 200 and r.json() == [], "en revisión no está en vacantes_publicas")
    pathlib.Path(ruta).write_text(json.dumps({"vacante": vacante, "titulo": titulo}))


def moderacion_correo(ruta: str) -> None:
    """El resumen en hola@, su enlace firmado y la aprobación."""
    datos = json.loads(pathlib.Path(ruta).read_text())
    texto = ""
    for _ in range(30):
        lista = httpx.get(
            f"{MAILPIT}/api/v1/search",
            params={"query": 'to:"hola@vectorhrtech.com"'},
            timeout=10,
        ).json()
        for mensaje in lista.get("messages", []):
            cuerpo = httpx.get(f"{MAILPIT}/api/v1/message/{mensaje['ID']}", timeout=10).json()
            if datos["titulo"] in cuerpo.get("Text", ""):
                texto = cuerpo["Text"]
                break
        if texto:
            break
        time.sleep(2)
    ok(bool(texto), "el resumen de la cola de revisión llega a hola@ (Mailpit)")
    ok("Manda a contactar por WhatsApp" in texto, "con el motivo de la vacante")
    enlace = re.search(r"Revisar: (\S+)", texto)
    ok(enlace is not None, "y su enlace de revisión")
    assert enlace is not None
    partes = urlsplit(enlace.group(1))
    ok(partes.path == "/moderacion/revisar", "el enlace va a /moderacion/revisar", partes.path)
    token = parse_qs(partes.query)["t"][0]

    r = http.get(f"{API}/moderacion/revisar", params={"t": token})
    ok(
        r.status_code == 200 and "Aprobar y publicar" in r.text,
        "el enlace abre la página de revisión por Caddy",
        r.status_code,
    )
    ok(r.headers.get("referrer-policy") == "no-referrer", "sin Referer: el token va en la URL")
    r = http.post(f"{API}/moderacion/revisar", data={"t": token, "accion": "aprobar"})
    ok(r.status_code == 200 and "Aprobada" in r.text, "Aprobar por POST", r.status_code)
    r = http.get(
        f"{API}/rest/v1/vacantes_publicas",
        params={"id": f"eq.{datos['vacante']}", "select": "id"},
        headers={"apikey": ANON},
    )
    ok(r.status_code == 200 and len(r.json()) == 1, "y ya está en vacantes_publicas")


if __name__ == "__main__":
    modo = sys.argv[2]
    if modo == "borde":
        borde()
        plantilla(sys.argv[3])
    elif modo == "alta":
        alta()
    elif modo == "career-site":
        career_site()
    elif modo == "moderacion-preparar":
        moderacion_preparar(sys.argv[3])
    elif modo == "moderacion-correo":
        moderacion_correo(sys.argv[3])
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
