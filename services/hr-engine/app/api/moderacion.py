"""La página de revisión de la cola de moderación (ADR-022).

El resumen a hola@ trae un enlace firmado por vacante (`app/security/
enlaces_de_revision.py`). Caddy publica solo `/moderacion/*` del hr-engine en
`api.` (con un tope de cuerpo chico).

- `GET /moderacion/revisar?t=…` solo muestra: la vacante, sus motivos y los dos
  botones. Los escáneres de correo abren los enlaces, así que un GET nunca cambia
  nada.
- `POST /moderacion/revisar` aplica la decisión: aprobar, o rechazar con un motivo
  que la empresa verá en su panel.

HTML sin JavaScript, con todo escapado (`html.escape`). El cuerpo del POST se
lee a mano (`application/x-www-form-urlencoded`) para no sumar python-multipart:
FastAPI lo pide para `Form()` ("Request Forms", fastapi.tiangolo.com/tutorial/
request-forms/).
"""

from __future__ import annotations

from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from app.application.moderar_vacantes import MotivoVacioError, ResolverRevision
from app.config import settings
from app.database import DbSession
from app.domain.moderacion import EstadoDeModeracion, VacanteEnCola
from app.infrastructure.moderacion import SqlRepositorioDeModeracion
from app.security import enlaces_de_revision

router = APIRouter()

#: El formulario trae un token, una acción y un motivo corto.
MAX_CUERPO = 16 * 1024

_CABECERAS = {
    # El token viaja en la URL: que no salga en el Referer ni quede en una caché.
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
        "frame-ancestors 'none'; base-uri 'none'"
    ),
}

_ESTADOS = {
    EstadoDeModeracion.PENDIENTE: "Pendiente de moderar",
    EstadoDeModeracion.PUBLICADA: "Publicada",
    EstadoDeModeracion.EN_REVISION: "En revisión",
    EstadoDeModeracion.RECHAZADA: "Rechazada",
    EstadoDeModeracion.OCULTA: "Oculta por reportes",
}

#: La respuesta cuando la vacante ya no estaba en la cola. Son textos fijos: el estado
#: solo elige cuál, así ningún dato de la petición se arma dentro del HTML.
_SIN_CAMBIOS = {
    estado: f"<h1>No se cambió nada</h1><p>La vacante está en: {escape(etiqueta)}.</p>"
    for estado, etiqueta in _ESTADOS.items()
}
_SIN_CAMBIOS_NO_EXISTE = "<h1>No se cambió nada</h1><p>La vacante ya no existe.</p>"

_ESTILO = """
body{font-family:system-ui,sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem;
color:#0b1020;line-height:1.5}h1{font-size:1.5rem;margin:.2rem 0}
.meta{color:#4b5563;font-size:.95rem}.motivos li{margin:.3rem 0}
.jd{white-space:pre-wrap;background:#f4f6f8;border-radius:12px;padding:1rem}
form{margin:1rem 0;padding:1rem;border:1px solid #d6dbe1;border-radius:12px}
button{font:inherit;font-weight:700;padding:.55rem 1rem;border-radius:10px;border:0;
cursor:pointer}.ok{background:#0e7c66;color:#fff}.no{background:#b42318;color:#fff}
textarea{width:100%;box-sizing:border-box;font:inherit;margin:.5rem 0}
"""


def _pagina(titulo: str, cuerpo: str, status_code: int = 200) -> HTMLResponse:
    html = (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(titulo)} · Vector HR Tech</title><style>{_ESTILO}</style></head>"
        f"<body><p class='meta'>VECTOR HR TECH · Revisión de vacantes</p>{cuerpo}</body></html>"
    )
    return HTMLResponse(html, status_code=status_code, headers=_CABECERAS)


def _invalido() -> HTMLResponse:
    return _pagina(
        "Enlace no válido",
        "<h1>Este enlace no sirve</h1><p>Venció (duran 7 días) o no está completo. "
        "La vacante sigue en la cola y sale en el próximo resumen, o se revisa con "
        "<code>python -m app.cli.moderacion cola</code>.</p>",
        status_code=403,
    )


def _sin_secreto() -> HTMLResponse:
    return _pagina(
        "Revisión no disponible",
        "<h1>La revisión no está configurada</h1><p>Falta MODERACION_SECRETO.</p>",
        status_code=503,
    )


def _ficha(v: VacanteEnCola, token: str) -> str:
    quien = (
        "Reclutador(a) independiente"
        if v.publica_para == "clientes"
        else ("Empresa verificada" if v.empresa_verificada else "Empresa sin verificar")
    )
    motivos = "".join(
        f"<li>{escape(m.senal)}" + (f" — <q>{escape(m.cita)}</q>" if m.cita else "") + "</li>"
        for m in v.motivos
    )
    t = escape(token, quote=True)
    acciones = (
        f"<form method='post' action='/moderacion/revisar'><input type='hidden' name='t' "
        f"value='{t}'><input type='hidden' name='accion' value='aprobar'>"
        "<button class='ok' type='submit'>Aprobar y publicar</button></form>"
        f"<form method='post' action='/moderacion/revisar'><input type='hidden' name='t' "
        f"value='{t}'><input type='hidden' name='accion' value='rechazar'>"
        "<label for='motivo'><b>Motivo del rechazo</b> (la empresa lo ve en su panel)</label>"
        "<textarea id='motivo' name='motivo' rows='3' maxlength='300' required></textarea>"
        "<button class='no' type='submit'>Rechazar</button></form>"
    )
    return (
        f"<h1>{escape(v.titulo)}</h1>"
        f"<p class='meta'>{escape(v.empresa)} · {quien} · {_ESTADOS[v.estado]}</p>"
        + (f"<h2>Motivos</h2><ul class='motivos'>{motivos}</ul>" if motivos else "")
        + f"<h2>Descripción</h2><div class='jd'>{escape(v.descripcion)}</div>"
        + acciones
    )


@router.get("/moderacion/revisar", response_class=HTMLResponse, include_in_schema=False)
async def ver(db: DbSession, t: str = Query(default="", max_length=200)) -> HTMLResponse:
    if not settings.moderacion_secreto:
        return _sin_secreto()
    vacante_id = enlaces_de_revision.verificar(settings.moderacion_secreto, t)
    if vacante_id is None:
        return _invalido()
    vacante = await SqlRepositorioDeModeracion(db).vacante_en_cola(vacante_id)
    if vacante is None:
        return _pagina("No existe", "<h1>La vacante ya no existe</h1>", status_code=404)
    return _pagina(vacante.titulo, _ficha(vacante, t))


@router.post("/moderacion/revisar", response_class=HTMLResponse, include_in_schema=False)
async def decidir(request: Request, db: DbSession) -> HTMLResponse:
    if not settings.moderacion_secreto:
        return _sin_secreto()
    cuerpo = await request.body()
    if len(cuerpo) > MAX_CUERPO:
        return _pagina("Demasiado largo", "<h1>El formulario es demasiado largo</h1>", 413)
    campos = parse_qs(cuerpo.decode("utf-8", errors="replace"), max_num_fields=5)
    token = (campos.get("t") or [""])[0]
    accion = (campos.get("accion") or [""])[0]
    motivo = (campos.get("motivo") or [""])[0]

    vacante_id = enlaces_de_revision.verificar(settings.moderacion_secreto, token)
    if vacante_id is None:
        return _invalido()
    repositorio = SqlRepositorioDeModeracion(db)
    caso = ResolverRevision(repositorio)
    if accion == "aprobar":
        hecho = await caso.aprobar(vacante_id)
        mensaje = "<h1>Aprobada</h1><p>Ya está en el career site.</p>"
    elif accion == "rechazar":
        try:
            hecho = await caso.rechazar(vacante_id, motivo)
        except MotivoVacioError:
            return _pagina(
                "Falta el motivo",
                "<h1>Falta el motivo</h1><p>Vuelve atrás y escribe por qué no se publica.</p>",
                422,
            )
        mensaje = "<h1>Rechazada</h1><p>La empresa verá el motivo en su panel.</p>"
    else:
        return _pagina("Acción no válida", "<h1>Acción no válida</h1>", 422)

    if not hecho:
        vacante = await repositorio.vacante_en_cola(vacante_id)
        sin_cambios = _SIN_CAMBIOS[vacante.estado] if vacante else _SIN_CAMBIOS_NO_EXISTE
        return _pagina("Sin cambios", sin_cambios, 409)
    return _pagina("Listo", mensaje)
