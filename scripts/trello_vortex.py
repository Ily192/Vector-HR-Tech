"""Tablero Trello de Vortex Ops: llenarlo y operar las tarjetas a medida que avanzan los PRs.

Uso (desde la raiz del repo):
  python scripts/trello_vortex.py poblar     llena el tablero (tiene que estar sin tarjetas)
  python scripts/trello_vortex.py estado
  python scripts/trello_vortex.py mover     "<parte del nombre de la tarjeta>" "<parte del nombre de la lista>"
  python scripts/trello_vortex.py comentar  "<parte del nombre de la tarjeta>" "<texto>"
  python scripts/trello_vortex.py adjuntar  "<parte del nombre de la tarjeta>" <url-o-ruta> [nombre]

Tablero: https://trello.com/b/Vxsv1fn7/vortexhr (se cambia con TRELLO_BOARD=<id o shortLink>).
Credenciales: TRELLO_KEY y TRELLO_TOKEN en var-local.env (raiz del repo, ignorado por git).
Nunca imprime la key ni el token.
"""

from __future__ import annotations

import json
import mimetypes
import pathlib
import sys
import textwrap
import time
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlencode

try:
    sys.stdout.reconfigure(encoding="utf-8")  # consola de Windows
except Exception:
    pass

REPO = pathlib.Path(__file__).resolve().parents[1]
API = "https://api.trello.com/1"
GH = "https://github.com/Ily192/Vector-HR-Tech/commit/"


# ─────────────────────────── credenciales y HTTP ───────────────────────────


def _env() -> dict[str, str]:
    out: dict[str, str] = {}
    for fname in ("var-local.env", "var-local.txt"):
        p = REPO / fname
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8-sig").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                out.setdefault(k.strip(), v.strip())
    return out


ENV = _env()
KEY, TOKEN = ENV.get("TRELLO_KEY"), ENV.get("TRELLO_TOKEN")
BOARD_REF = ENV.get("TRELLO_BOARD", "Vxsv1fn7")
BOARD_DESC = (
    "Desarrollo de Vortex Ops (Vector HR Tech). Shape Up + flujo Kanban por PR: "
    "cada tarjeta es un PR. Las reglas están en la lista 📌."
)


def _multipart(fields: dict, files: dict) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n').encode()
    for k, (fname, content, mime) in files.items():
        body += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode() + content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def api(method: str, path: str, params: dict | None = None, files: dict | None = None):
    if not KEY or not TOKEN:
        raise SystemExit("Faltan TRELLO_KEY y/o TRELLO_TOKEN en var-local.env")
    params = {k: v for k, v in (params or {}).items() if v is not None}
    url = f"{API}{path}?{urlencode({'key': KEY, 'token': TOKEN})}"
    headers = {"Accept": "application/json"}
    data = None
    if method == "GET":
        if params:
            url += "&" + urlencode(params)
    elif files:
        data, headers["Content-Type"] = _multipart(params, files)
    elif params:
        data = urlencode(params).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    for intento in range(6):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                time.sleep(0.12)  # limite: 100 peticiones cada 10 s por token
                raw = r.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2**intento)
                continue
            detalle = e.read().decode("utf-8", "replace")[:300]
            raise SystemExit(f"Trello {method} {path} -> HTTP {e.code}: {detalle}") from None
    raise SystemExit("Trello: demasiados 429 seguidos")


def _board() -> dict:
    return api("GET", f"/boards/{BOARD_REF}", {"fields": "name,url,desc"})


def d(texto: str) -> str:
    return textwrap.dedent(texto).strip()


def commits(*shas: str) -> str:
    return "**Commits:**\n" + "\n".join(f"- [`{s}`]({GH}{s})" for s in shas)


# ─────────────────────────────── el tablero ───────────────────────────────

LISTAS = [
    "📌 Cómo usar este tablero",
    "🧊 Aparcado · sin apuesta",
    "🗺️ Ruta · próximas fases",
    "🎯 Apostado · fase actual",
    "⛰️ Descubriendo (WIP 2 con Construyendo)",
    "🔨 Construyendo (WIP 2 con Descubriendo)",
    "👀 PR en revisión (WIP 3)",
    "✅ Hecho",
]
GUIA, APARCADO, RUTA, APOSTADO, DESCUBRIENDO, CONSTRUYENDO, REVISION, HECHO = LISTAS

ETIQUETAS = [
    ("F0 · Tapar lo silencioso", "red"),
    ("F1 · Clean Architecture", "orange"),
    ("F2 · Next 16 + Supabase + 2.1", "yellow"),
    ("F3 · Validación con Siete", "green"),
    ("F4 · Decisiones de negocio", "blue"),
    ("🔒 Seguridad / compliance", "purple"),
    ("💼 Negocio", "lime"),
    ("🧾 Deuda técnica", "pink"),
    ("📜 Histórico", "sky"),
    ("🚫 Bloqueado", "black"),
]
F0, F1, F2, F3, F4, SEG, NEG, DEUDA, HIST, BLOQ = (e[0] for e in ETIQUETAS)

CA = "Criterios de aceptación"

TARJETAS: list[dict] = [
    # ── Guía ──────────────────────────────────────────────────────────────
    {
        "lista": GUIA,
        "nombre": "Cómo funciona este tablero",
        "desc": d("""
            ## Metodología: Shape Up + flujo Kanban por PR

            El proyecto ya trabaja con **Shape Up adaptado** (`docs/02_METHODOLOGY.md`): se *apuesta* por un bloque de trabajo con apetito definido, sin backlog infinito y con enfriamiento entre bloques. Este tablero le suma un **flujo Kanban**: cada PR se mueve de izquierda a derecha, con límites de trabajo en curso.

            Las fases de la ruta (F0-F4) son las apuestas. **Cada tarjeta es un PR.**

            ## Columnas y cuándo se entra

            | Columna | Qué significa | Para entrar |
            |---|---|---|
            | 🧊 Aparcado | Ideas y deuda sin apuesta | — |
            | 🗺️ Ruta | PRs de fases futuras, por prioridad | Tener fase asignada |
            | 🎯 Apostado | La fase en curso. Arriba = lo siguiente | Empezó la fase |
            | ⛰️ Descubriendo | Subiendo la colina: aún hay incógnitas | Definition of Ready |
            | 🔨 Construyendo | Bajando la colina: ya se sabe qué hacer | Enfoque decidido |
            | 👀 PR en revisión | PR abierto: comentarios y capturas aquí | PR adjunto a la tarjeta |
            | ✅ Hecho | Mergeado, desplegado y verificado | Definition of Done |

            ⛰️ y 🔨 son la *hill chart* de Shape Up: una tarjeta que lleva días sin bajar la colina es la señal para recortar alcance.

            ## Límites de trabajo en curso

            - ⛰️ + 🔨: **máximo 2** tarjetas a la vez.
            - 👀 PR en revisión: **máximo 3**. Si está lleno, se revisa antes de empezar algo nuevo.

            ## Reglas

            - **Una tarjeta = un PR.** El título de la tarjeta es el título del PR (Conventional Commits).
            - El enlace al PR va como adjunto; los comentarios y capturas de la revisión, en la tarjeta.
            - Una tarjeta bloqueada lleva 🚫 Bloqueado y un comentario con el motivo. No vuelve hacia atrás.
            - Nada pasa a ✅ Hecho sin su checklist de criterios completo.
        """),
    },
    {
        "lista": GUIA,
        "nombre": "Plantilla de tarjeta y de PR",
        "desc": d("""
            Misma estructura en la tarjeta y en la descripción del PR:

            - **Problema** — qué pasa hoy y cómo se sabe (evidencia).
            - **Enfoque** — 3 a 5 líneas: qué se va a cambiar.
            - **Riesgos** — qué puede romperse.
            - **Criterios de aceptación** — checklist verificable.
            - **Evidencia** — capturas, salida de tests, preview.
            - **Enlaces** — PR, commits, docs.

            Etiquetas: la fase (F0-F4) y, si aplica, 🔒 Seguridad / 💼 Negocio / 🧾 Deuda técnica.
        """),
    },
    {
        "lista": GUIA,
        "nombre": "Definition of Ready y Definition of Done",
        "desc": "Resumen de `docs/11_QUALITY_GATES.md`. El detalle por tipo de cambio (DB, skill, UI, seguridad, CI) está ahí.",
        "checklists": {
            "DoR — antes de mover a ⛰️ Descubriendo": [
                "Problema y evidencia escritos en la tarjeta",
                "Enfoque en 3-5 líneas",
                "Riesgos identificados",
                "Criterios de aceptación verificables",
            ],
            "DoD — antes de mover a ✅ Hecho": [
                "Lint y typecheck en verde",
                "Tests pasan y la cobertura no baja",
                "PR con descripción completa (y capturas si toca UI)",
                "Revisado (humano o agente de code review)",
                "Docs y next-steps actualizados",
                "Desplegado y verificado",
            ],
        },
    },
    {
        "lista": GUIA,
        "nombre": "🗺️ Ruta y fases",
        "desc": d("""
            Orden acordado el 2026-09-14: **por prioridad**. Sale de la auditoría del proyecto contra sus skills.

            | Fase | Objetivo | Se sale cuando |
            |---|---|---|
            | F0 · Tapar lo silencioso | Corregir lo que falla sin avisar | Test de regresión del event loop en verde y ningún siguiente paso decidido sin política |
            | F1 · Clean Architecture | EvaluateCandidate en capas, como plantilla | Caso de uso probado con adaptadores falsos y worker fino |
            | F2 · Next 16 + Supabase + 2.1 | Cerrar el DoD del Cycle 1 sobre suelo firme | Subir CV en career-site → score visible en < 2 min, de punta a punta |
            | F3 · Validación con Siete | Uso real con criterios escritos | Criterios de éxito cumplidos o aprendizajes documentados |
            | F4 · Decisiones de negocio | Segmento, precio y continuidad antes de ensanchar | ICP validado y unidad de precio decidida |
        """),
    },
    {
        "lista": GUIA,
        "nombre": "❓ Decisiones pendientes",
        "labels": [NEG],
        "checklists": {
            "Por decidir": [
                "Segmento principal — hipótesis: consultoras de selección / RPO tipo Siete (validar en F3-F4)",
                "Unidad operativa de precio (vacantes activas o candidatos evaluados; nunca tokens)",
                "Regla de continuidad cuando se agota el presupuesto",
                "force row level security: ¿el owner tiene BYPASSRLS en Supabase?",
                "Un solo camino de escritura para runs",
                "¿Portal de candidato dentro de career-site en vez de una tercera app?",
                "Plan de Supabase: free sin PITR o Pro con backups",
            ]
        },
    },
    # ── En curso ahora mismo ──────────────────────────────────────────────
    {
        "lista": REVISION,
        "nombre": "[F0·0] chore(skills): skills del taller y de ingeniería como Claude skills",
        "labels": [F0],
        "desc": d("""
            **Qué hace.**
            - Formaliza `official-docs-alignment` y `clean-architecture-refactor` como Claude skills del proyecto en `.claude/skills/`, con frontmatter válido.
            - Las 35 skills del taller quedan como skills **personales** en `~/.claude/skills/`, fuera del repo: son material del taller sin licencia de redistribución y el repo es público. Único cambio: el `description` entrecomillado, porque el YAML original era inválido.
            - La carpeta fuente `/skills/` sale de git.

            **Evidencia.** 37/37 pasan `skills-ref validate`, el validador oficial de Agent Skills. Antes: 0/37.
        """),
        "checklists": {CA: [
            "37/37 skills válidas",
            "Las skills del proyecto aparecen en una sesión nueva de Claude Code",
            "La carpeta fuente no entra en git",
        ]},
    },
    {
        "lista": CONSTRUYENDO,
        "nombre": "[F0·0b] chore(pm): tablero de Trello como código",
        "labels": [F0],
        "desc": d("""
            `scripts/trello_vortex.py` llena este tablero y lo opera: `estado`, `mover`, `comentar` y `adjuntar`. Lee las credenciales de `var-local.env` y nunca las imprime.

            La rama `chore/trello-tablero` está subida como respaldo. El PR se abre cuando haya llenado el tablero de verdad: la primera ejecución es su prueba.
        """),
        "checklists": {CA: [
            "El tablero se llenó completo con el script",
            "mover, comentar y adjuntar probados sobre una tarjeta real",
            "Ninguna credencial en el repo ni en la salida",
        ]},
    },
    # ── F0 · Apostado (orden = prioridad) ─────────────────────────────────
    {
        "lista": APOSTADO,
        "nombre": "[F0·1] fix(hr-engine): motor sin pool para los workers de Celery",
        "labels": [F0],
        "desc": d("""
            **Problema.** El motor async de SQLAlchemy se crea una vez al importar (`app/database.py:37`) y cada tarea de Celery abre un event loop nuevo con `asyncio.run`. Las conexiones del pool quedan atadas al loop anterior: **una de cada dos tareas falla** con `RuntimeError: Event loop is closed`.

            **Evidencia.** Reproducido el 2026-09-14 con el `db_session()` real contra Postgres: 3 corridas de 4 tareas, fallan siempre la 1 y la 3. Con `NullPool`, 12/12. La documentación oficial de SQLAlchemy lo advierte (*Using multiple asyncio event loops*).

            **Enfoque.** Motor dedicado con `NullPool` para los workers; la API conserva el motor con pool. La reproducción se convierte en test de regresión.

            **Riesgos.** Una conexión nueva por tarea: despreciable frente a la latencia del LLM.
        """),
        "checklists": {CA: [
            "Test de regresión que falla sin el fix y pasa con él",
            "4 o más tareas seguidas en el mismo proceso sin error",
            "La API sigue usando el motor con pool",
            "cv_evaluator y sourcer usan el motor de workers",
        ]},
    },
    {
        "lista": APOSTADO,
        "nombre": "[F0·2] fix(hr-engine): un run nunca se queda en pending si falla antes del claim",
        "labels": [F0],
        "desc": d("""
            **Problema.** En `workers/cv_evaluator.py:163`, `claim_run` está fuera del `try`. Si falla ahí —como pasa con el bug del event loop— el run no se marca `failed`: queda `pending` para siempre y la aplicación sin evaluar, sin rastro en los datos. Además `RuntimeError` no cuenta como transitorio, así que Celery no reintenta.

            **Enfoque.** Todo lo que ocurre después de registrar el run pasa por el manejo de errores que lo marca `failed`. Revisar qué errores son transitorios. Mismo patrón en `sourcer`.
        """),
        "checklists": {CA: [
            "Un fallo en el claim deja el run en failed con mensaje",
            "Test que lo cubre",
            "Mismo comportamiento en sourcer",
        ]},
    },
    {
        "lista": APOSTADO,
        "nombre": "[F0·3] fix(cv-evaluator): el prompt sale del SKILL.md, con calibración y regla anti-sesgo",
        "labels": [F0, SEG],
        "desc": d("""
            **Problema.** Ningún runtime lee los SKILL.md. El prompt real está escrito a mano en `clients/scoring.py:69` y **no incluye** la calibración del score ni la regla *"ignorá edad, género, nacionalidad"* del SKILL.md. En un producto de HR es riesgo de compliance.

            **Enfoque.** Cargar las instrucciones desde `.agents/skills/cv-evaluator/SKILL.md`, o declararlas en código con un test que las exija. Una sola fuente de verdad.
        """),
        "checklists": {CA: [
            "El prompt que recibe el modelo incluye la calibración y la regla anti-sesgo",
            "Test que falla si se quitan",
            "SKILL.md y código dejan de divergir en modelo y reglas",
        ]},
    },
    {
        "lista": APOSTADO,
        "nombre": "[F0·4] feat(hr-engine): política determinista del siguiente paso según el score",
        "labels": [F0, SEG],
        "desc": d("""
            **Problema.** `recommended_next_step` (rechazar / psicométrico / entrevista) lo elige el modelo sin reglas, y nada comprueba que cuadre con el score: un 8.5 con "rechazar" se acepta. Es una decisión sobre una persona en manos de un LLM sin instrucciones.

            **Enfoque.** `NextStepPolicy` en dominio: < 4 rechazar, 4-6 psicométrico, ≥ 7 entrevista (umbrales del SKILL.md). El modelo aporta score y razonamiento; la política decide. Es el primer ladrillo de la capa de dominio de F1.
        """),
        "checklists": {CA: [
            "Política con tests en los bordes (3.99 · 4 · 6.99 · 7)",
            "El siguiente paso guardado sale de la política, no del modelo",
            "Las discrepancias modelo↔política quedan registradas",
        ]},
    },
    {
        "lista": APOSTADO,
        "nombre": "[F0·5] fix(types): contrato de CvEvaluation igual en Zod y Pydantic",
        "labels": [F0],
        "desc": d("""
            **Problema.** `scoring.py` dice que "espejea" `packages/types/src/hr.ts`, pero no hay test y no coinciden: Zod usa `candidate_id` y el worker `candidato_id`; `rationale` exige mínimo 1 en Zod y 10 en Pydantic.

            **Enfoque.** Una sola definición (o generación desde JSON Schema) y un test de contrato que compare los dos lados.
        """),
        "checklists": {CA: [
            "Mismos nombres y restricciones en los dos lados",
            "Test de contrato en CI",
        ]},
    },
    {
        "lista": APOSTADO,
        "nombre": "[F0·6] docs: deriva entre documentación y código",
        "labels": [F0],
        "desc": d("""
            **Problema.** Lo declarado no es lo ejecutado:
            - ADR-008 y los SKILL.md citan `gemini-1.5-flash` (retirado) y precios viejos; el código usa `gemini-2.5-flash`.
            - El fallback a `gpt-4o-mini` que declaran las skills no existe, ni `app/providers/` de ADR-008.
            - `workers/run_state.py:4` dice que `runs` solo tiene policy de lectura (0004 lo corrigió).
            - 3 de las 4 dependencias de datos de hrbp no se importan en ningún sitio.

            **Enfoque.** Caso por caso: o el documento describe lo que hay, o se implementa lo que declara.
        """),
        "checklists": {CA: [
            "ADR-008 y SKILL.md con el modelo y precios vigentes",
            "Fallback: implementado o retirado de la documentación",
            "Docstring de run_state corregido",
            "Dependencias de hrbp: usadas o eliminadas",
        ]},
    },
    {
        "lista": APOSTADO,
        "nombre": "[F0·7] docs(runbook): la base de pruebas usa un puerto propio y falla si no arranca",
        "labels": [F0],
        "desc": d("""
            **Problema.** El bloque del runbook usa el 5432, que ocupa `backend-db-1` de otro proyecto. Si `docker run` falla, el bloque sigue y pytest intenta conectar a otra base. La guarda `_assert_disposable` solo mira el nombre de la base.

            **Enfoque.** Puerto dedicado (55432), comprobación explícita de que el contenedor arrancó, y `DATABASE_URL` coherente en el runbook.
        """),
        "checklists": {CA: [
            "El bloque aborta si el contenedor no arranca",
            "Puerto propio documentado",
            "Probado dos veces seguidas en esta máquina",
        ]},
    },
    # ── F1 · Ruta ─────────────────────────────────────────────────────────
    {
        "lista": RUTA,
        "nombre": "[F1·1] refactor(hr-engine): capa de dominio de la evaluación",
        "labels": [F1],
        "desc": "Entidades (`Candidato`, `Vacante`, `FitScore`), `NextStepPolicy` (viene de F0·4) y puertos: `CandidateRepository`, `EmbeddingProvider`, `ScoringProvider`, `CostBudget`. Sin imports de SQLAlchemy, Celery ni SDKs.",
        "checklists": {CA: [
            "Domain sin imports de infraestructura, verificado por test",
            "Tests unitarios puros del dominio",
        ]},
    },
    {
        "lista": RUTA,
        "nombre": "[F1·2] refactor(hr-engine): caso de uso EvaluateCandidate",
        "labels": [F1],
        "desc": "Orquesta la evaluación a través de los puertos: embeddings si faltan, scoring, política, persistencia y costo. Se prueba con adaptadores falsos, sin base ni red.",
        "checklists": {CA: [
            "Caso de uso cubierto con adaptadores falsos",
            "Mismo resultado que el worker actual en los tests existentes",
        ]},
    },
    {
        "lista": RUTA,
        "nombre": "[F1·3] refactor(hr-engine): adaptadores de infraestructura y worker fino",
        "labels": [F1],
        "desc": "Repositorio SQLAlchemy (incluye el SQL crudo que hoy vive en el worker), adaptadores Gemini y OpenAI, y la tarea de Celery como adaptador de entrada que solo traduce. La API deja de importar el worker: encola a través de un puerto.",
        "checklists": {CA: [
            "Worker de menos de 50 líneas",
            "Sin SQL fuera de los repositorios",
            "La API no importa el worker",
            "Tests unitarios y de seguridad en verde",
        ]},
    },
    {
        "lista": RUTA,
        "nombre": "[F1·4] refactor(hr-engine): sourcer sobre la misma plantilla",
        "labels": [F1],
        "desc": "Aplicar a `sourcer` la estructura de F1·1 a F1·3. Si la plantilla no encaja, se ajusta aquí y no antes.",
    },
    {
        "lista": RUTA,
        "nombre": "[F1·5] chore(skills): SKILL.md de producto alineados con el estándar Agent Skills",
        "labels": [F1],
        "desc": d("""
            **Problema.** Las skills de Vortex usan 8 campos fuera del estándar (`version`, `owner`, `domain`, `inputs`, `outputs`, `models`, `cost_cap_usd`, `tags`) y el validador oficial las rechaza. `skills-sdk` no tiene consumidores. ADR-006 promete `evals/`, `SKILL.md.tmpl` y `README.md` por skill, y no existen.

            **Enfoque.** Campos propios en `metadata` o en un sidecar `agents/vortex.yaml` (como ya existe `agents/openai.yaml`). Actualizar ADR-006 y el SDK.
        """),
        "checklists": {CA: [
            "skills-ref validate en verde para las skills de producto",
            "ADR-006 actualizado",
            "skills-sdk valida el formato nuevo",
        ]},
    },
    # ── F2 · Ruta ─────────────────────────────────────────────────────────
    {
        "lista": RUTA,
        "nombre": "[F2·1] chore(career-site): Next 14 → 16 y React 19",
        "labels": [F2, SEG],
        "desc": d("""
            **Problema.** Next 14 está sin soporte de seguridad desde el 26-oct-2025 y career-site es público. Next 15 pierde soporte el 21-oct-2026: se va directo a 16.

            **Enfoque.** Codemods oficiales (`upgrade latest` y `next-async-request-api`). Punto de ruptura conocido: el `params` síncrono de `vacantes/[slug]/page.tsx:24`.
        """),
        "checklists": {CA: [
            "Build y tests en verde",
            "E2E smoke en verde",
            "Preview en Vercel correcto",
            "Lighthouse ≥ 85",
        ]},
    },
    {
        "lista": RUTA,
        "nombre": "[F2·2] chore(infra): Supabase Cloud con las migraciones 0001..0006",
        "labels": [F2],
        "desc": d("""
            Proyecto en `sa-east-1`, extensión `vector`, `supabase db push`, hook de JWT activado y primer admin de plataforma.

            **Conexión.** La directa es solo IPv6 salvo que se pague el add-on de IPv4. Con el pooler en modo transacción, asyncpg necesita `statement_cache_size=0`.

            De paso: contestar si el owner tiene `BYPASSRLS` (decide F4·4).
        """),
        "checklists": {CA: [
            "Migraciones aplicadas sin error",
            "Hook de JWT activo y probado",
            "Modo de conexión elegido y documentado",
            "Respuesta sobre BYPASSRLS anotada",
        ]},
    },
    {
        "lista": RUTA,
        "nombre": "[F2·3] chore(infra): secrets en GitHub Actions y variables en Vercel",
        "labels": [F2],
        "desc": "Las variables `NEXT_PUBLIC_*` y `VITE_*` en Vercel, y los secrets del CI (Supabase, proveedores de IA, Vercel, Sentry, Codecov).",
    },
    {
        "lista": RUTA,
        "nombre": "[F2·4] chore(infra): hr-engine desplegado en Fly.io",
        "labels": [F2],
        "desc": "ADR-012 eligió Fly.io y no hay `fly.toml` ni step de `flyctl` en ningún workflow. Sin backend desplegado no hay DoD de punta a punta.",
    },
    {
        "lista": RUTA,
        "nombre": "[F2·5] feat(career-site): formulario de aplicación con subida de CV (2.1)",
        "labels": [F2],
        "desc": "Server Action + bucket `cvs` + RPC `aplicar_a_vacante` (el SQL ya está en 0005). Los datos de vacantes pasan por un puerto `VacantesRepository` en vez de los mocks actuales.",
        "checklists": {CA: [
            "El candidato aplica y la application queda creada",
            "El CV queda en el bucket bajo la ruta de su empresa",
            "Sin mocks: vacantes desde el repositorio",
            "Capturas del formulario (móvil y escritorio)",
        ]},
    },
    {
        "lista": RUTA,
        "nombre": "[F2·6] feat(career-site): rate limit y captcha en aplicar_a_vacante",
        "labels": [F2, SEG],
        "desc": "Antes de exponer el formulario público: la RPC es invocable por `anon` y hoy no tiene ninguna capa anti-abuso.",
    },
    {
        "lista": RUTA,
        "nombre": "[F2·7] test(e2e): subir CV → score visible en menos de 2 minutos",
        "labels": [F2],
        "desc": "El DoD del Cycle 1 como test de Playwright sobre el entorno desplegado.",
    },
    # ── F3 · Ruta ─────────────────────────────────────────────────────────
    {
        "lista": RUTA,
        "nombre": "[F3·1] negocio: plan de validación con Siete",
        "labels": [F3, NEG],
        "desc": "Skill `plan-de-validacion`. Criterios de éxito escritos en términos de negocio antes de empezar (el DoD actual es técnico) y quién participa de cada lado.",
    },
    {
        "lista": RUTA,
        "nombre": "[F3·2] negocio: mapa de onboarding de Siete y primer valor",
        "labels": [F3, NEG],
        "desc": "Skills `mapa-de-onboarding` y `estrategia-de-despliegue`: el estado actual, las fotos intermedias y en cuál ocurre el primer valor tangible. Despliegue beta con usuarios capaces, no encendido total.",
    },
    {
        "lista": RUTA,
        "nombre": "[F3·3] chore(infra): backups y staging antes de datos reales",
        "labels": [F3],
        "desc": "Hoy se promueve de CI directo a producción y la única estrategia de backups (PITR) es del plan Pro. Con candidatos reales no se puede operar así.",
    },
    {
        "lista": RUTA,
        "nombre": "[F3·4] feat(compliance): consentimiento y retención mínimos (LGPD / Habeas Data)",
        "labels": [F3, SEG],
        "desc": "Antes de procesar candidatos reales: consentimiento, retención por tipo de dato, exportación y borrado. El esquema hoy no tiene nada de eso (`docs/08` lo promete).",
    },
    {
        "lista": RUTA,
        "nombre": "[F3·5] negocio: 5 a 10 entrevistas de descubrimiento con consultoras tipo Siete",
        "labels": [F3, NEG],
        "desc": "Skills `icp-y-senales` (ruta hipótesis) y `guion-de-descubrimiento`. Con cero clientes que hayan pagado, el ICP se descubre en conversaciones antes de invertir en pauta o en más módulos.",
    },
    {
        "lista": RUTA,
        "nombre": "[F3·6] docs: demo en Loom de 5 minutos (2.8)",
        "labels": [F3],
        "desc": "Grabar el flujo real de punta a punta una vez cerrado F2.",
    },
    # ── F4 · Ruta ─────────────────────────────────────────────────────────
    {
        "lista": RUTA,
        "nombre": "[F4·1] negocio: ICP validado y segmento principal",
        "labels": [F4, NEG],
        "desc": "Hipótesis actual: consultoras de selección y RPO pequeñas y medianas en LATAM que reclutan para varias empresas cliente — el perfil de Siete. Se valida con F3·5.",
    },
    {
        "lista": RUTA,
        "nombre": "[F4·2] negocio: unidad operativa de precio y paquetes",
        "labels": [F4, NEG],
        "desc": "Skill `pricing-de-ia`. El pricing v2 cuenta \"jobs HR/mes\" y \"empresas\" por plan: afinar a una unidad que el cliente entienda (vacantes activas o candidatos evaluados), con bolsa y excedente. Nunca tokens.",
    },
    {
        "lista": RUTA,
        "nombre": "[F4·3] feat(hr-engine): regla de continuidad cuando se agota el presupuesto",
        "labels": [F4],
        "desc": "Hoy `CostCapExceededError` corta la ejecución en seco: es el \"bloqueo de proceso\" que `pricing-de-ia` prohíbe. Antes de los presupuestos por tenant: degradar a un modelo más barato o diferir, sin detener el proceso del cliente.",
    },
    {
        "lista": RUTA,
        "nombre": "[F4·4] fix(db): decidir force row level security",
        "labels": [F4, SEG],
        "desc": "Depende de la respuesta sobre `BYPASSRLS` de F2·2. Ver `0004` §9.",
    },
    {
        "lista": RUTA,
        "nombre": "[F4·5] refactor(hr-engine): un solo camino de escritura para runs",
        "labels": [F4],
        "desc": "Hoy conviven la sesión sin contexto de tenant y la policy `runs_tenant_write`. ADR-004 pide la segunda (defensa en profundidad).",
    },
    # ── Aparcado ──────────────────────────────────────────────────────────
    *[
        {"lista": APARCADO, "nombre": n, "labels": [DEUDA], "desc": desc}
        for n, desc in [
            ("2.2 · Portal de candidato — evaluar fusionarlo con career-site", "Misma audiencia y su flujo empieza en career-site (aplicar → estado → test): una app menos."),
            ("2.3 · Kanban HRBP con @dnd-kit y Realtime", "Hoy App.tsx son KPIs escritos a mano."),
            ("2.4 · Skill chro-intake", "SKILL.md + golden set."),
            ("2.5 · Golden set con ≥ 10 CVs reales y evaluador conectado al modelo", "Hoy hay 8 casos y `_run_cv_evaluator()` lanza excepción a propósito."),
            ("Skills HR restantes: psicométrico, entrevistador, onboarder", "El charter promete 6 skills HR y existen 2."),
            ("Sales engine multi-tenant", "Las 11 skills de prospección del taller son, en la práctica, su especificación."),
            ("Tailwind 3 → 4 (configuración CSS-first)", "El preset JS habría que cargarlo con `@config`."),
            ("Acotar con TO authenticated las 20 policies restantes", "Solo una rompía (0006 §2). Las otras son coste de planner y una mina a futuro."),
            ("Feature flags, Doppler, OpenTelemetry y branch protection", "Referenciados en la documentación y sin integrar."),
            ("Recall de pgvector: filtrar por empresa_id en el SQL", "RLS se aplica después del scan del índice."),
            ("activity_log: cadena de hash real, particionado y purga", "Hoy la cadena de hash es decorativa."),
            ("Cifrado de columna: raw_answers y transcript", "`docs/08` dice que deberían ir cifrados."),
        ]
    ],
    # ── Hecho (antes del tablero) ─────────────────────────────────────────
    {
        "lista": HECHO,
        "nombre": "Sesión 5 · career-site y hrbp desplegados en Vercel",
        "labels": [HIST],
        "desc": d("""
            Dos proyectos enlazados al repo; cada push a `main` despliega solo.
            - https://vortex-career-site.vercel.app
            - https://vortex-hrbp.vercel.app

            El primer intento falló por un `ignoreCommand` que llamaba a un binario inexistente.
        """) + "\n\n" + commits("1a3f0b8", "416e843"),
    },
    {
        "lista": HECHO,
        "nombre": "Sesión 5 · Repo publicado en GitHub",
        "labels": [HIST],
        "desc": "Force-push de `main` a `Ily192/Vector-HR-Tech`; el scaffold anterior quedó en el tag `legacy/ai-studio-scaffold`. Verificado: ningún secreto entre los objetos publicados.\n\n" + commits("6d61dcb", "617e5b4"),
    },
    {
        "lista": HECHO,
        "nombre": "Sesión 5 · Token de GitHub fuera de git",
        "labels": [HIST, SEG],
        "desc": "`var-local.txt` y `var-local.env` estaban sin trackear y sin ignorar en un repo público.\n\n" + commits("c4ced74"),
    },
    {
        "lista": HECHO,
        "nombre": "Sesión 5 · Auditoría del registro: compose de dev, shim y cobertura",
        "labels": [HIST],
        "desc": "El compose de desarrollo montaba solo hasta 0005, su shim arrastraba el bug de `auth.uid()` y la mitad del fix de 0006 no la ejecutaba ningún test.\n\n" + commits("e0acf05", "5b19f75"),
    },
    {
        "lista": HECHO,
        "nombre": "Sesión 4 · RLS contra Postgres real: tres bugs de esquema (0006)",
        "labels": [HIST, SEG],
        "desc": "Primera ejecución real de las migraciones y de los tests de RLS. El test psicométrico estaba muerto por dos bugs en serie.\n\n" + commits("bf76adb", "36fa30e"),
    },
    {
        "lista": HECHO,
        "nombre": "Sesión 3 · hr-engine arranca, se autentica y persiste los runs",
        "labels": [HIST],
        "desc": commits("b046cf3"),
    },
    {
        "lista": HECHO,
        "nombre": "Sesión 3 · Escaladas multi-tenant cerradas y gates que pueden fallar",
        "labels": [HIST, SEG],
        "desc": "Tres vías por las que un anónimo tomaba control de un tenant (0004, 0005), tests de seguridad y un CI que ya puede fallar.\n\n" + commits("caacc49", "42d42f9"),
    },
    {
        "lista": HECHO,
        "nombre": "Sesión 3 · El monorepo compila por primera vez + lockfiles",
        "labels": [HIST],
        "desc": commits("4474f9b"),
    },
]


# ─────────────────────────────── comandos ───────────────────────────────


def poblar() -> None:
    board = _board()
    bid = board["id"]

    ya = api("GET", f"/boards/{bid}/cards", {"fields": "name"})
    if ya:
        raise SystemExit(f"El tablero ya tiene {len(ya)} tarjetas; no lo toco. Revísalo con `estado`.")

    # Las listas que traiga el tablero están vacías (se acaba de comprobar): se archivan,
    # no se borran, así que se pueden recuperar desde el menú del tablero.
    archivadas = 0
    for lst in api("GET", f"/boards/{bid}/lists", {"filter": "open", "fields": "name"}):
        api("PUT", f"/lists/{lst['id']}/closed", {"value": "true"})
        archivadas += 1

    # Las etiquetas de colores sin nombre que trae Trello por defecto se reutilizan.
    sin_nombre: dict[str, str] = {}
    for lab in api("GET", f"/boards/{bid}/labels", {"fields": "name,color"}):
        if not lab.get("name") and lab.get("color"):
            sin_nombre.setdefault(lab["color"], lab["id"])
    etiquetas: dict[str, str] = {}
    reutilizadas = 0
    for nombre, color in ETIQUETAS:
        if color in sin_nombre:
            lid = sin_nombre.pop(color)
            api("PUT", f"/labels/{lid}", {"name": nombre})
            reutilizadas += 1
        else:
            lid = api("POST", f"/boards/{bid}/labels", {"name": nombre, "color": color})["id"]
        etiquetas[nombre] = lid

    if not board.get("desc"):
        api("PUT", f"/boards/{bid}", {"desc": BOARD_DESC})

    listas = {n: api("POST", f"/boards/{bid}/lists", {"name": n, "pos": "bottom"})["id"] for n in LISTAS}

    n_items = 0
    for t in TARJETAS:
        card = api("POST", "/cards", {
            "idList": listas[t["lista"]],
            "name": t["nombre"],
            "desc": t.get("desc", ""),
            "idLabels": ",".join(etiquetas[e] for e in t.get("labels", [])) or None,
            "pos": "bottom",
        })
        for nombre_cl, items in t.get("checklists", {}).items():
            cl = api("POST", "/checklists", {"idCard": card["id"], "name": nombre_cl})
            for it in items:
                api("POST", f"/checklists/{cl['id']}/checkItems", {"name": it, "checked": "false"})
                n_items += 1

    print(f"Tablero lleno: {board['url']}")
    print(f"  listas archivadas: {archivadas} · etiquetas reutilizadas: {reutilizadas}")
    print(f"  {len(LISTAS)} listas · {len(ETIQUETAS)} etiquetas · {len(TARJETAS)} tarjetas · {n_items} items de checklist")


def _buscar_tarjeta(bid: str, texto: str) -> dict:
    cards = api("GET", f"/boards/{bid}/cards", {"fields": "name,idList,shortUrl"})
    hits = [c for c in cards if texto.lower() in c["name"].lower()]
    if len(hits) != 1:
        nombres = "\n  ".join(c["name"] for c in hits) or "(ninguna)"
        raise SystemExit(f"'{texto}' coincide con {len(hits)} tarjetas:\n  {nombres}")
    return hits[0]


def _buscar_lista(bid: str, texto: str) -> dict:
    lists = api("GET", f"/boards/{bid}/lists", {"fields": "name"})
    hits = [lst for lst in lists if texto.lower() in lst["name"].lower()]
    if len(hits) != 1:
        raise SystemExit(f"'{texto}' coincide con {len(hits)} listas")
    return hits[0]


def mover(texto_card: str, texto_lista: str) -> None:
    bid = _board()["id"]
    card, lista = _buscar_tarjeta(bid, texto_card), _buscar_lista(bid, texto_lista)
    api("PUT", f"/cards/{card['id']}", {"idList": lista["id"], "pos": "top"})
    print(f"Movida: {card['name']}  →  {lista['name']}")


def comentar(texto_card: str, comentario: str) -> None:
    bid = _board()["id"]
    card = _buscar_tarjeta(bid, texto_card)
    api("POST", f"/cards/{card['id']}/actions/comments", {"text": comentario})
    print(f"Comentado: {card['name']}")


def adjuntar(texto_card: str, recurso: str, nombre: str | None) -> None:
    bid = _board()["id"]
    card = _buscar_tarjeta(bid, texto_card)
    p = pathlib.Path(recurso)
    if recurso.startswith(("http://", "https://")):
        api("POST", f"/cards/{card['id']}/attachments", {"url": recurso, "name": nombre})
    elif p.is_file():
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        api("POST", f"/cards/{card['id']}/attachments", {"name": nombre or p.name},
            files={"file": (p.name, p.read_bytes(), mime)})
    else:
        raise SystemExit(f"No es una URL ni un fichero: {recurso}")
    print(f"Adjuntado a: {card['name']}")


def estado() -> None:
    board = _board()
    bid = board["id"]
    lists = api("GET", f"/boards/{bid}/lists", {"fields": "name"})
    cards = api("GET", f"/boards/{bid}/cards", {"fields": "name,idList"})
    print(board["url"])
    for lst in lists:
        propias = [c["name"] for c in cards if c["idList"] == lst["id"]]
        print(f"\n{lst['name']}  ({len(propias)})")
        for n in propias:
            print(f"  · {n}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    cmd, rest = args[0], args[1:]
    if cmd == "poblar" and not rest:
        poblar()
    elif cmd == "estado" and not rest:
        estado()
    elif cmd == "mover" and len(rest) == 2:
        mover(*rest)
    elif cmd == "comentar" and len(rest) == 2:
        comentar(*rest)
    elif cmd == "adjuntar" and len(rest) in (2, 3):
        adjuntar(rest[0], rest[1], rest[2] if len(rest) == 3 else None)
    else:
        raise SystemExit(__doc__)
