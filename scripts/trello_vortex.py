"""Tablero Trello de Vortex Ops en Scrumban: llenarlo y operarlo a medida que avanzan los PRs.

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
GH = "https://github.com/Ily192/Vector-HR-Tech"


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
    "Desarrollo de Vortex Ops (Vector HR Tech). Scrumban: flujo Kanban con límites de "
    "trabajo en curso + sprints de dos semanas. Cada tarjeta es un PR. Reglas en la lista 📌."
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
        raise SystemExit(
            "Faltan TRELLO_KEY y/o TRELLO_TOKEN en var-local.env.\n"
            "No sirve un API token de Atlassian (ATATT...): la API de Trello necesita\n"
            "la key del Power-Up (32 caracteres) y su token (ATTA..., ~76 caracteres)."
        )
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
    return "**Commits:** " + " · ".join(f"[`{s}`]({GH}/commit/{s})" for s in shas)


# ─────────────────────────────── el tablero ───────────────────────────────

LISTAS = [
    "📌 Cómo usar este tablero",
    "🗃️ Backlog (lo que falta)",
    "🎯 Listo para sprint",
    "🏃 Sprint 1 · 1-14 oct",
    "🔨 En curso (WIP 2)",
    "👀 PR en revisión (WIP 3)",
    "🧪 Verificación",
    "✅ Hecho",
    "📜 Histórico (antes del tablero)",
]
GUIA, BACKLOG, LISTO, SPRINT, CURSO, REVISION, VERIF, HECHO, HIST_L = LISTAS

ETIQUETAS = [
    # Proyectos: cada landing, web o servicio es un proyecto aparte
    ("🌐 career-site (web pública)", "sky"),
    ("🖥️ hrbp (cockpit)", "lime"),
    ("👤 candidate (portal)", "pink"),
    ("⚙️ hr-engine (backend)", "blue"),
    ("🗄️ datos · Supabase", "purple"),
    ("🤖 agentes · skills", "orange"),
    ("🛠️ plataforma · CI/CD", "black"),
    # Transversales
    ("🔒 Seguridad / compliance", "red"),
    ("💼 Negocio", "green"),
    ("🧾 Deuda técnica", "yellow"),
    ("🚫 Bloqueado", "red"),
    ("S2 · 15-28 oct", "sky"),
    ("S3 · 29 oct-11 nov", "lime"),
]
(CAREER, HRBP, CANDIDATE, ENGINE, DATOS, AGENTES, PLAT,
 SEG, NEG, DEUDA, BLOQ, S2, S3) = (e[0] for e in ETIQUETAS)

CA = "Criterios de aceptación"

TARJETAS: list[dict] = [
    # ── Guía ──────────────────────────────────────────────────────────────
    {
        "lista": GUIA,
        "nombre": "Cómo funciona este tablero (Scrumban)",
        "desc": d("""
            ## Scrumban = flujo Kanban + cadencia de sprints

            Del **Kanban**: el trabajo se tira (no se empuja), hay límites de trabajo en curso y las tarjetas avanzan de izquierda a derecha.
            Del **Scrum**: hay un sprint de dos semanas con un objetivo, y una revisión al cerrarlo.

            Encaja con lo que el proyecto ya declara en `docs/02_METHODOLOGY.md` (ciclos de dos semanas, trunk-based, un dev) sin las ceremonias de Scrum completo.

            ## Columnas

            | Columna | Qué contiene |
            |---|---|
            | 🗃️ Backlog | Todo lo que falta, ordenado: arriba lo más prioritario |
            | 🎯 Listo para sprint | Cumple la Definition of Ready; entra en el próximo sprint |
            | 🏃 Sprint | Lo comprometido para estas dos semanas |
            | 🔨 En curso | Lo que se está haciendo ahora. **Máximo 2** |
            | 👀 PR en revisión | PR abierto: comentarios y capturas aquí. **Máximo 3** |
            | 🧪 Verificación | Mergeado pero sin comprobar en el entorno real |
            | ✅ Hecho | Verificado funcionando |
            | 📜 Histórico | Lo que ya estaba hecho antes de existir el tablero |

            ## Reglas

            - **Una tarjeta = un PR.** El título de la tarjeta es el título del PR (Conventional Commits).
            - **Se tira, no se empuja:** solo se saca una tarjeta nueva del sprint cuando se libera un hueco en 🔨.
            - **Nada entra a 🏃 sin DoR**, y nada sale a ✅ sin DoD ni sin verificar.
            - Una tarjeta parada lleva 🚫 Bloqueado y un comentario con el motivo y de quién depende.
            - Cuando 🎯 se queda con menos de 3 tarjetas, toca repasar el backlog.

            ## Cada landing y cada web son un proyecto aparte

            Las etiquetas de color identifican el proyecto: career-site, hrbp, candidate, hr-engine, datos, agentes y plataforma. Una tarjeta puede tocar dos (por ejemplo, el E2E toca career-site y hr-engine).
        """),
    },
    {
        "lista": GUIA,
        "nombre": "🏃 Sprints y objetivos",
        "desc": d("""
            Sprints de dos semanas. El objetivo es una frase, no una lista: si al cerrar el sprint no se puede decir que se cumplió, el sprint no se cumplió.

            | Sprint | Fechas | Objetivo |
            |---|---|---|
            | **S1** | 1-14 oct | Ninguna evaluación se pierde en silencio, y el tablero refleja la realidad del proyecto |
            | **S2** | 15-28 oct | `EvaluateCandidate` en capas como plantilla, y career-site fuera de una versión sin soporte |
            | **S3** | 29 oct-11 nov | El DoD del Cycle 1 de punta a punta: subir CV → score visible en menos de 2 minutos |

            Después de S3 vienen la validación con Siete y las decisiones de negocio (ICP, unidad de precio), que están en el backlog.

            **Cierre de sprint:** mover a ✅ lo verificado, devolver al backlog lo que no se hizo (no se arrastra en silencio) y anotar en `docs/runbooks/session-log.md` qué se aprendió.
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

            Etiquetas: el proyecto que toca y, si aplica, 🔒 Seguridad · 💼 Negocio · 🧾 Deuda técnica · 🚫 Bloqueado.
        """),
    },
    {
        "lista": GUIA,
        "nombre": "Definition of Ready y Definition of Done",
        "desc": "Resumen de `docs/11_QUALITY_GATES.md`. El detalle por tipo de cambio (DB, skill, UI, seguridad, CI) está ahí.",
        "checklists": {
            "DoR — para entrar al sprint": [
                "Problema y evidencia escritos en la tarjeta",
                "Enfoque en 3-5 líneas",
                "Riesgos identificados",
                "Criterios de aceptación verificables",
                "Proyecto etiquetado",
            ],
            "DoD — para pasar a ✅ Hecho": [
                "Lint y typecheck en verde",
                "Tests pasan y la cobertura no baja",
                "PR con descripción completa (y capturas si toca UI)",
                "Revisado (humano o agente de code review)",
                "Docs y next-steps actualizados",
                "Desplegado y comprobado en el entorno real",
            ],
        },
    },
    {
        "lista": GUIA,
        "nombre": "❓ Decisiones pendientes",
        "labels": [NEG],
        "checklists": {
            "Por decidir": [
                "Segmento principal — hipótesis: consultoras de selección / RPO tipo Siete",
                "Unidad operativa de precio (vacantes activas o candidatos evaluados; nunca tokens)",
                "Regla de continuidad cuando se agota el presupuesto",
                "force row level security: ¿el owner tiene BYPASSRLS en Supabase?",
                "Un solo camino de escritura para runs",
                "¿Portal de candidato dentro de career-site en vez de una tercera app?",
                "Plan de Supabase: free sin PITR o Pro con backups",
                "¿Entran al tablero las otras landings y webs (Krono, Aura, Vivi, Katalog, CRM-Cloo)?",
            ]
        },
    },
    # ── Sprint 1 ──────────────────────────────────────────────────────────
    {
        "lista": SPRINT,
        "nombre": "[S1] 🚫 Desbloquear: credenciales de la API de Trello",
        "labels": [PLAT, BLOQ],
        "desc": d("""
            **Depende de Ilyra.** En `var-local.env` hay un `API_TOKEN_TRELLO` que es un *API token de Atlassian* (`ATATT…`, 192 caracteres, de id.atlassian.com). La API de Trello lo rechaza con 401 de las tres formas probadas.

            Hacen falta dos valores distintos, de https://trello.com/apps/admin → Power-Up:
            - `TRELLO_KEY`: 32 caracteres.
            - `TRELLO_TOKEN`: empieza por `ATTA`, unos 76 caracteres (enlace *Token* → Permitir).

            Sin esto, este tablero no se puede actualizar desde el repo.
        """),
        "checklists": {CA: ["TRELLO_KEY y TRELLO_TOKEN en var-local.env", "`poblar` y `estado` funcionan"]},
    },
    {
        "lista": SPRINT,
        "nombre": "[S1] 🚫 Desbloquear: permiso de Pull requests en el token de GitHub",
        "labels": [PLAT, BLOQ],
        "desc": d("""
            **Depende de Ilyra.** Al PAT fine-grained le falta `Pull requests: Read and write`. Sin él, `gh pr create` responde `Resource not accessible by personal access token (createPullRequest)` — comprobado el 14-sep y de nuevo el 1-oct.

            Se añade en https://github.com/settings/personal-access-tokens, donde ya tiene Contents y Workflows. Tres ramas están subidas esperando su PR.
        """),
        "checklists": {CA: ["El token abre PRs", "Abiertos los PR de las tres ramas pendientes"]},
    },
    {
        "lista": SPRINT,
        "nombre": "[S1] fix(hr-engine): motor sin pool para los workers de Celery",
        "labels": [ENGINE],
        "desc": d("""
            **Problema.** El motor async de SQLAlchemy se crea al importar (`app/database.py:37`) y cada tarea de Celery abre un event loop nuevo con `asyncio.run`. Las conexiones del pool quedan atadas al loop anterior: **una de cada dos tareas falla** con `RuntimeError: Event loop is closed`.

            **Evidencia.** Reproducido contra Postgres con el `db_session()` real: 3 corridas de 4 tareas, fallan siempre la 1 y la 3. Con `NullPool`, 12/12. Lo advierte la documentación oficial de SQLAlchemy (*Using multiple asyncio event loops*).

            **Enfoque.** Motor dedicado con `NullPool` para los workers; la API conserva el motor con pool. La reproducción se convierte en test de regresión.
        """),
        "checklists": {CA: [
            "Test de regresión que falla sin el fix y pasa con él",
            "4 o más tareas seguidas en el mismo proceso sin error",
            "La API sigue usando el motor con pool",
            "cv_evaluator y sourcer usan el motor de workers",
        ]},
    },
    {
        "lista": SPRINT,
        "nombre": "[S1] fix(hr-engine): un run nunca se queda en pending si falla antes del claim",
        "labels": [ENGINE],
        "desc": d("""
            **Problema.** En `workers/cv_evaluator.py:163`, `claim_run` está fuera del `try`. Si falla ahí, el run no se marca `failed`: queda `pending` para siempre y la aplicación sin evaluar, sin rastro. Además `RuntimeError` no cuenta como transitorio, así que Celery no reintenta.

            **Enfoque.** Todo lo posterior a registrar el run pasa por el manejo de errores que lo marca `failed`. Revisar la clasificación de errores transitorios. Mismo patrón en `sourcer`.
        """),
        "checklists": {CA: [
            "Un fallo en el claim deja el run en failed con mensaje",
            "Test que lo cubre",
            "Mismo comportamiento en sourcer",
        ]},
    },
    {
        "lista": SPRINT,
        "nombre": "[S1] fix(cv-evaluator): el prompt sale del SKILL.md, con calibración y regla anti-sesgo",
        "labels": [AGENTES, ENGINE, SEG],
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
        "lista": SPRINT,
        "nombre": "[S1] feat(hr-engine): política determinista del siguiente paso según el score",
        "labels": [ENGINE, SEG],
        "desc": d("""
            **Problema.** `recommended_next_step` (rechazar / psicométrico / entrevista) lo elige el modelo sin reglas, y nada comprueba que cuadre con el score: un 8.5 con "rechazar" se acepta. Es una decisión sobre una persona en manos de un LLM sin instrucciones.

            **Enfoque.** `NextStepPolicy` en dominio: < 4 rechazar, 4-6 psicométrico, ≥ 7 entrevista. El modelo aporta score y razonamiento; la política decide. Primer ladrillo de la capa de dominio del sprint 2.
        """),
        "checklists": {CA: [
            "Política con tests en los bordes (3.99 · 4 · 6.99 · 7)",
            "El siguiente paso guardado sale de la política, no del modelo",
            "Las discrepancias modelo↔política quedan registradas",
        ]},
    },
    {
        "lista": SPRINT,
        "nombre": "[S1] fix(types): contrato de CvEvaluation igual en Zod y Pydantic",
        "labels": [PLAT],
        "desc": d("""
            **Problema.** `scoring.py` dice que "espejea" `packages/types/src/hr.ts`, pero no hay test y no coinciden: Zod usa `candidate_id` y el worker `candidato_id`; `rationale` exige mínimo 1 en Zod y 10 en Pydantic.

            **Enfoque.** Una sola definición (o generación desde JSON Schema) y un test de contrato.
        """),
        "checklists": {CA: ["Mismos nombres y restricciones en los dos lados", "Test de contrato en CI"]},
    },
    {
        "lista": SPRINT,
        "nombre": "[S1] chore(deps): triaje de los 16 PRs de Dependabot",
        "labels": [PLAT, DEUDA],
        "desc": d("""
            Dependabot abrió 16 PRs el 10-sep y siguen abiertos. Hay que decidir uno por uno: mergear, agrupar o cerrar.

            Ojo con dos: **next 14.2.35 → 16.3.4** (es la tarjeta de career-site del sprint 2, no se mergea a ciegas) y el grupo de **react**, que arrastra React 19. El resto (actions, tooling, types, postcss, commitlint, changesets, size-limit, lucide, supabase/ssr, python 3.14) son más mecánicos.

            El CI tiene que estar en verde en cada uno antes de mergear.
        """),
        "checklists": {CA: [
            "Cada PR: mergeado, agrupado o cerrado con razón",
            "next y react quedan ligados a sus tarjetas de producto",
            "CI en verde tras el merge",
        ]},
    },
    {
        "lista": SPRINT,
        "nombre": "[S1] docs: deriva entre documentación y código",
        "labels": [PLAT],
        "desc": d("""
            Lo declarado no es lo ejecutado:
            - ADR-008 y los SKILL.md citan `gemini-1.5-flash` (retirado) y precios viejos; el código usa `gemini-2.5-flash`.
            - El fallback a `gpt-4o-mini` que declaran las skills no existe, ni `app/providers/` de ADR-008.
            - `workers/run_state.py:4` dice que `runs` solo tiene policy de lectura (0004 lo corrigió).
            - 3 de las 4 dependencias de datos de hrbp no se importan en ningún sitio.
        """),
        "checklists": {CA: [
            "ADR-008 y SKILL.md con el modelo y precios vigentes",
            "Fallback: implementado o retirado de la documentación",
            "Docstring de run_state corregido",
            "Dependencias de hrbp: usadas o eliminadas",
        ]},
    },
    {
        "lista": SPRINT,
        "nombre": "[S1] docs(runbook): la base de pruebas usa un puerto propio y falla si no arranca",
        "labels": [PLAT],
        "desc": d("""
            El bloque del runbook usa el 5432, que ocupa `backend-db-1` de otro proyecto. Si `docker run` falla, el bloque sigue y pytest intenta conectar a otra base. La guarda `_assert_disposable` solo mira el nombre de la base.
        """),
        "checklists": {CA: [
            "El bloque aborta si el contenedor no arranca",
            "Puerto propio documentado",
            "Probado dos veces seguidas en esta máquina",
        ]},
    },
    # ── En curso / revisión ───────────────────────────────────────────────
    {
        "lista": CURSO,
        "nombre": "[S1] chore(pm): tablero de Trello como código",
        "labels": [PLAT],
        "desc": d("""
            `scripts/trello_vortex.py` llena este tablero y lo opera: `estado`, `mover`, `comentar` y `adjuntar`. Lee las credenciales de `var-local.env` y nunca las imprime.

            Rama `chore/trello-tablero` subida. La primera ejecución contra la API es su prueba.
        """),
        "checklists": {CA: [
            "El tablero se llenó completo con el script",
            "mover, comentar y adjuntar probados sobre una tarjeta real",
            "Ninguna credencial en el repo ni en la salida",
        ]},
    },
    {
        "lista": REVISION,
        "nombre": "[S1] chore(skills): skills del taller y de ingeniería como Claude skills",
        "labels": [AGENTES, BLOQ],
        "desc": d("""
            Las dos skills de ingeniería pasan a `.claude/skills/` del proyecto con frontmatter válido; las 35 del taller quedan como skills personales en `~/.claude/skills/`, fuera del repo (material sin licencia de redistribución, y el repo es público). La carpeta fuente `/skills/` sale de git.

            **Evidencia:** 37/37 pasan `skills-ref validate`. Antes: 0/37.

            🚫 Rama `chore/claude-skills` subida (`843e32e`); **el PR no se puede abrir** hasta que el token tenga permiso de Pull requests.
        """),
        "checklists": {CA: ["37/37 skills válidas", "PR abierto y revisado", "La carpeta fuente no entra en git"]},
    },
    {
        "lista": REVISION,
        "nombre": "[S1] docs(runbooks): sesión 6 — auditoría contra las skills y ruta por fases",
        "labels": [PLAT, BLOQ],
        "desc": d("""
            Registro de la sesión 6 y `next-steps` reorganizado: bloqueos, metodología y la ruta por fases. Responde por qué están separadas las apps y cuál es el mejor cliente según el benchmark.

            🚫 Rama `docs/sesion-6` subida (`fb30036`); el PR espera el permiso de Pull requests.
        """),
    },
    # ── Listo para sprint (S2) ────────────────────────────────────────────
    {
        "lista": LISTO,
        "nombre": "[S2] chore(career-site): Next 14 → 16 y React 19",
        "labels": [CAREER, SEG, S2],
        "desc": d("""
            **Problema.** Next 14 está sin soporte de seguridad desde el 26-oct-2025 y career-site es público. Next 15 lo pierde el 21-oct-2026: se va directo a 16.

            **Enfoque.** Codemods oficiales (`upgrade latest` y `next-async-request-api`). Punto de ruptura conocido: el `params` síncrono de `vacantes/[slug]/page.tsx:24`. Dependabot ya abrió el PR del bump; esta tarjeta es la que lo valida de verdad.
        """),
        "checklists": {CA: [
            "Build y tests en verde",
            "E2E smoke en verde",
            "Preview en Vercel correcto",
            "Lighthouse ≥ 85",
        ]},
    },
    {
        "lista": LISTO,
        "nombre": "[S2] refactor(hr-engine): capa de dominio de la evaluación",
        "labels": [ENGINE, S2],
        "desc": "Entidades (`Candidato`, `Vacante`, `FitScore`), `NextStepPolicy` (viene del sprint 1) y puertos: `CandidateRepository`, `EmbeddingProvider`, `ScoringProvider`, `CostBudget`. Sin imports de SQLAlchemy, Celery ni SDKs.",
        "checklists": {CA: ["Domain sin imports de infraestructura, verificado por test", "Tests unitarios puros del dominio"]},
    },
    {
        "lista": LISTO,
        "nombre": "[S2] refactor(hr-engine): caso de uso EvaluateCandidate",
        "labels": [ENGINE, S2],
        "desc": "Orquesta la evaluación a través de los puertos: embeddings si faltan, scoring, política, persistencia y costo. Se prueba con adaptadores falsos, sin base ni red.",
        "checklists": {CA: ["Caso de uso cubierto con adaptadores falsos", "Mismo resultado que el worker actual en los tests existentes"]},
    },
    {
        "lista": LISTO,
        "nombre": "[S2] refactor(hr-engine): adaptadores de infraestructura y worker fino",
        "labels": [ENGINE, S2],
        "desc": "Repositorio SQLAlchemy (incluye el SQL crudo que hoy vive en el worker), adaptadores Gemini y OpenAI, y la tarea de Celery como adaptador que solo traduce. La API deja de importar el worker.",
        "checklists": {CA: [
            "Worker de menos de 50 líneas",
            "Sin SQL fuera de los repositorios",
            "La API no importa el worker",
            "Tests unitarios y de seguridad en verde",
        ]},
    },
    # ── Backlog ───────────────────────────────────────────────────────────
    {
        "lista": BACKLOG,
        "nombre": "[S2] refactor(hr-engine): sourcer sobre la misma plantilla",
        "labels": [ENGINE, S2],
        "desc": "Aplicar a `sourcer` la estructura del caso de uso ancla. Si la plantilla no encaja, se ajusta aquí y no antes.",
    },
    {
        "lista": BACKLOG,
        "nombre": "[S2] chore(skills): SKILL.md de producto alineados con el estándar Agent Skills",
        "labels": [AGENTES, S2],
        "desc": d("""
            Las skills de Vortex usan 8 campos fuera del estándar y el validador oficial las rechaza. `skills-sdk` no tiene consumidores, y ADR-006 promete `evals/`, `SKILL.md.tmpl` y `README.md` por skill que no existen.

            Campos propios a `metadata` o a un sidecar `agents/vortex.yaml`, como ya existe `agents/openai.yaml`.
        """),
    },
    {
        "lista": BACKLOG,
        "nombre": "[S3] chore(infra): Supabase Cloud con las migraciones 0001..0006",
        "labels": [DATOS, S3],
        "desc": d("""
            Proyecto en `sa-east-1`, extensión `vector`, `supabase db push`, hook de JWT activado y primer admin de plataforma.

            **Conexión:** la directa es solo IPv6 salvo add-on de pago; con el pooler en modo transacción, asyncpg necesita `statement_cache_size=0`. De paso, contestar si el owner tiene `BYPASSRLS`.
        """),
        "checklists": {CA: [
            "Migraciones aplicadas sin error",
            "Hook de JWT activo y probado",
            "Modo de conexión elegido y documentado",
            "Respuesta sobre BYPASSRLS anotada",
        ]},
    },
    {
        "lista": BACKLOG,
        "nombre": "[S3] chore(infra): secrets en GitHub Actions y variables en Vercel",
        "labels": [PLAT, S3],
        "desc": "Las `NEXT_PUBLIC_*` y `VITE_*` en Vercel, y los secrets del CI (Supabase, proveedores de IA, Vercel, Sentry, Codecov).",
    },
    {
        "lista": BACKLOG,
        "nombre": "[S3] chore(infra): hr-engine desplegado en Fly.io",
        "labels": [ENGINE, S3],
        "desc": "ADR-012 eligió Fly.io y no hay `fly.toml` ni step de `flyctl`. Sin backend desplegado no hay DoD de punta a punta.",
    },
    {
        "lista": BACKLOG,
        "nombre": "[S3] feat(career-site): formulario de aplicación con subida de CV",
        "labels": [CAREER, S3],
        "desc": "Server Action + bucket `cvs` + RPC `aplicar_a_vacante` (el SQL ya está en 0005). Las vacantes pasan por un puerto `VacantesRepository` en vez de los mocks actuales.",
        "checklists": {CA: [
            "El candidato aplica y la application queda creada",
            "El CV queda en el bucket bajo la ruta de su empresa",
            "Sin mocks: vacantes desde el repositorio",
            "Capturas del formulario (móvil y escritorio)",
        ]},
    },
    {
        "lista": BACKLOG,
        "nombre": "[S3] feat(career-site): rate limit y captcha en aplicar_a_vacante",
        "labels": [CAREER, SEG, S3],
        "desc": "Antes de exponer el formulario público: la RPC es invocable por `anon` y no tiene ninguna capa anti-abuso.",
    },
    {
        "lista": BACKLOG,
        "nombre": "[S3] test(e2e): subir CV → score visible en menos de 2 minutos",
        "labels": [CAREER, ENGINE, S3],
        "desc": "El DoD del Cycle 1 como test de Playwright sobre el entorno desplegado.",
    },
    {
        "lista": BACKLOG,
        "nombre": "negocio: plan de validación con Siete",
        "labels": [NEG],
        "desc": "Skill `plan-de-validacion`. Criterios de éxito escritos en términos de negocio antes de empezar (el DoD actual es técnico) y quién participa de cada lado.",
    },
    {
        "lista": BACKLOG,
        "nombre": "negocio: mapa de onboarding de Siete y primer valor",
        "labels": [NEG],
        "desc": "Skills `mapa-de-onboarding` y `estrategia-de-despliegue`: estado actual, fotos intermedias y en cuál ocurre el primer valor tangible. Despliegue beta, no encendido total.",
    },
    {
        "lista": BACKLOG,
        "nombre": "negocio: 5 a 10 entrevistas de descubrimiento con consultoras tipo Siete",
        "labels": [NEG],
        "desc": "Skills `icp-y-senales` (ruta hipótesis) y `guion-de-descubrimiento`. Con cero clientes que hayan pagado, el ICP se descubre en conversaciones antes de invertir en pauta o en más módulos.",
    },
    {
        "lista": BACKLOG,
        "nombre": "negocio: ICP validado y segmento principal",
        "labels": [NEG],
        "desc": "Hipótesis: consultoras de selección y RPO pequeñas y medianas de LATAM que reclutan para varias empresas cliente — el perfil de Siete.",
    },
    {
        "lista": BACKLOG,
        "nombre": "negocio: unidad operativa de precio y paquetes",
        "labels": [NEG],
        "desc": "Skill `pricing-de-ia`. El pricing v2 cuenta \"jobs HR/mes\" y \"empresas\": afinar a una unidad que el cliente entienda (vacantes activas o candidatos evaluados), con bolsa y excedente. Nunca tokens.",
    },
    {
        "lista": BACKLOG,
        "nombre": "chore(infra): backups y staging antes de datos reales",
        "labels": [DATOS],
        "desc": "Hoy se promueve de CI directo a producción y la única estrategia de backups (PITR) es del plan Pro. Con candidatos reales no se puede operar así.",
    },
    {
        "lista": BACKLOG,
        "nombre": "feat(compliance): consentimiento y retención mínimos (LGPD / Habeas Data)",
        "labels": [DATOS, SEG],
        "desc": "Antes de procesar candidatos reales: consentimiento, retención por tipo de dato, exportación y borrado. El esquema no tiene nada de eso (`docs/08` lo promete).",
    },
    {
        "lista": BACKLOG,
        "nombre": "feat(hr-engine): regla de continuidad cuando se agota el presupuesto",
        "labels": [ENGINE],
        "desc": "Hoy `CostCapExceededError` corta en seco: es el \"bloqueo de proceso\" que prohíbe `pricing-de-ia`. Degradar a un modelo más barato o diferir, sin detener el proceso del cliente.",
    },
    {
        "lista": BACKLOG,
        "nombre": "fix(db): decidir force row level security",
        "labels": [DATOS, SEG],
        "desc": "Depende de la respuesta sobre `BYPASSRLS` al provisionar Supabase. Ver `0004` §9.",
    },
    {
        "lista": BACKLOG,
        "nombre": "refactor(hr-engine): un solo camino de escritura para runs",
        "labels": [ENGINE],
        "desc": "Hoy conviven la sesión sin contexto de tenant y la policy `runs_tenant_write`. ADR-004 pide la segunda.",
    },
    {
        "lista": BACKLOG,
        "nombre": "docs: demo en Loom de 5 minutos",
        "labels": [PLAT],
        "desc": "Grabar el flujo real de punta a punta cuando el DoD del Cycle 1 esté cerrado.",
    },
    {
        "lista": BACKLOG,
        "nombre": "feat(candidate): portal del candidato — evaluar fusionarlo con career-site",
        "labels": [CANDIDATE],
        "desc": "Rutas `/`, `/applications/:id`, `/test/:token`, `/profile`. Misma audiencia que career-site y su flujo empieza ahí: conviene meterlo como rutas autenticadas de career-site en vez de una tercera app.",
    },
    {
        "lista": BACKLOG,
        "nombre": "feat(hrbp): kanban de vacantes con @dnd-kit y Realtime",
        "labels": [HRBP],
        "desc": "Hoy `App.tsx` son 100 líneas con KPIs escritos a mano y tres dependencias de datos sin usar.",
    },
    {
        "lista": BACKLOG,
        "nombre": "feat(agentes): skill chro-intake",
        "labels": [AGENTES],
        "desc": "SKILL.md + golden set. El charter promete 6 skills HR y existen 2.",
    },
    {
        "lista": BACKLOG,
        "nombre": "feat(agentes): golden set con ≥ 10 CVs reales y evaluador conectado al modelo",
        "labels": [AGENTES],
        "desc": "Hoy hay 8 casos y `_run_cv_evaluator()` lanza excepción a propósito.",
    },
    {
        "lista": BACKLOG,
        "nombre": "feat(agentes): skills HR restantes — psicométrico, entrevistador, onboarder",
        "labels": [AGENTES],
        "desc": "Las tres que faltan para las 6 del charter.",
    },
    {
        "lista": BACKLOG,
        "nombre": "feat: sales engine multi-tenant",
        "labels": [PLAT],
        "desc": "Las 11 skills de prospección del taller son, en la práctica, su especificación.",
    },
    {
        "lista": BACKLOG,
        "nombre": "chore(career-site, hrbp): Tailwind 3 → 4 (configuración CSS-first)",
        "labels": [CAREER, HRBP, DEUDA],
        "desc": "El preset JS habría que cargarlo con `@config`.",
    },
    {
        "lista": BACKLOG,
        "nombre": "fix(db): acotar con TO authenticated las 20 policies restantes",
        "labels": [DATOS, DEUDA],
        "desc": "Solo una rompía (0006 §2). Las otras son coste de planner y una mina a futuro.",
    },
    {
        "lista": BACKLOG,
        "nombre": "chore(plataforma): feature flags, Doppler, OpenTelemetry y branch protection",
        "labels": [PLAT, DEUDA],
        "desc": "Referenciados en la documentación y sin integrar.",
    },
    {
        "lista": BACKLOG,
        "nombre": "fix(db): recall de pgvector — filtrar por empresa_id en el SQL",
        "labels": [DATOS, DEUDA],
        "desc": "RLS se aplica después del scan del índice: un tenant chico puede recibir 0 resultados teniendo candidatos perfectos.",
    },
    {
        "lista": BACKLOG,
        "nombre": "fix(db): activity_log — cadena de hash real, particionado y purga",
        "labels": [DATOS, DEUDA],
        "desc": "Hoy la cadena de hash no la calcula ni valida nada: es decorativa.",
    },
    {
        "lista": BACKLOG,
        "nombre": "fix(db): cifrado de columna en raw_answers y transcript",
        "labels": [DATOS, SEG, DEUDA],
        "desc": "`docs/08` dice que deberían ir cifrados y están en claro.",
    },
    # ── Histórico ─────────────────────────────────────────────────────────
    {
        "lista": HIST_L,
        "nombre": "Sesión 5 · career-site y hrbp desplegados en Vercel",
        "labels": [CAREER, HRBP],
        "desc": d("""
            Dos proyectos enlazados al repo; cada push a `main` despliega solo.
            - https://vortex-career-site.vercel.app
            - https://vortex-hrbp.vercel.app
        """) + "\n\n" + commits("1a3f0b8", "416e843"),
    },
    {
        "lista": HIST_L,
        "nombre": "Sesión 5 · Repo publicado en GitHub",
        "labels": [PLAT],
        "desc": "Force-push de `main` a `Ily192/Vector-HR-Tech`; el scaffold anterior quedó en el tag `legacy/ai-studio-scaffold`. Verificado: ningún secreto entre los objetos publicados.\n\n" + commits("6d61dcb", "617e5b4"),
    },
    {
        "lista": HIST_L,
        "nombre": "Sesión 5 · Token de GitHub fuera de git",
        "labels": [PLAT, SEG],
        "desc": "`var-local.txt` y `var-local.env` estaban sin trackear y sin ignorar en un repo público.\n\n" + commits("c4ced74"),
    },
    {
        "lista": HIST_L,
        "nombre": "Sesión 5 · Auditoría del registro: compose de dev, shim y cobertura",
        "labels": [DATOS, PLAT],
        "desc": "El compose de desarrollo montaba solo hasta 0005, su shim arrastraba el bug de `auth.uid()` y la mitad del fix de 0006 no la ejecutaba ningún test.\n\n" + commits("e0acf05", "5b19f75"),
    },
    {
        "lista": HIST_L,
        "nombre": "Sesión 4 · RLS contra Postgres real: tres bugs de esquema (0006)",
        "labels": [DATOS, SEG],
        "desc": "Primera ejecución real de las migraciones y de los tests de RLS. El test psicométrico estaba muerto por dos bugs en serie.\n\n" + commits("bf76adb", "36fa30e"),
    },
    {
        "lista": HIST_L,
        "nombre": "Sesión 3 · hr-engine arranca, se autentica y persiste los runs",
        "labels": [ENGINE],
        "desc": commits("b046cf3"),
    },
    {
        "lista": HIST_L,
        "nombre": "Sesión 3 · Escaladas multi-tenant cerradas y gates que pueden fallar",
        "labels": [DATOS, SEG],
        "desc": "Tres vías por las que un anónimo tomaba control de un tenant (0004, 0005), tests de seguridad y un CI que ya puede fallar.\n\n" + commits("caacc49", "42d42f9"),
    },
    {
        "lista": HIST_L,
        "nombre": "Sesión 3 · El monorepo compila por primera vez + lockfiles",
        "labels": [PLAT],
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

    archivadas = 0
    for lst in api("GET", f"/boards/{bid}/lists", {"filter": "open", "fields": "name"}):
        api("PUT", f"/lists/{lst['id']}/closed", {"value": "true"})
        archivadas += 1

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
    print(f"  {len(LISTAS)} listas · {len(ETIQUETAS)} etiquetas · {len(TARJETAS)} tarjetas · {n_items} items")


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
