"""Moderación de vacantes y verificación de empresas, sin IA (ADR-022).

El alta en el plan gratis es automática: cualquiera puede abrir una cuenta y
publicar. Antes de que una vacante salga al career site, el hr-engine la pasa
por reglas fijas que buscan las señales de las vacantes falsas de siempre (cobrar
un curso, pedir datos bancarios, mandar a un WhatsApp) y decide con el contexto
de la empresa: si está verificada, si publica para clientes, si es su primera
vacante.

Las reglas no juzgan el puesto ni a la empresa: buscan frases. Cada marca trae
la frase citada, para que la empresa sepa qué corregir y Vector HR vea por qué.
La duda se resuelve hacia la revisión humana, nunca hacia el rechazo: solo una
señal de gravedad alta rechaza sin revisión.

Moderación interna, no es una función de IA para el cliente. El PR 3 suma un
modelo por el puerto `RevisorDeVacantes`: sus marcas se agregan a las de las
reglas y la decisión no cambia.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID

# ─────────────────────────────── estados y marcas ───────────────────────────────


class EstadoDeModeracion(StrEnum):
    """Los valores del enum `public.moderacion_vacante` (migración 0019)."""

    PENDIENTE = "pendiente"
    PUBLICADA = "publicada"
    EN_REVISION = "en_revision"
    RECHAZADA = "rechazada"
    OCULTA = "oculta"


class Gravedad(IntEnum):
    #: Informa por qué una vacante va a revisión (reclutador, primera vacante).
    BAJA = 0
    #: Va a revisión humana.
    MEDIA = 1
    #: Se rechaza sin revisión.
    ALTA = 2

    @property
    def etiqueta(self) -> str:
        return ("baja", "media", "alta")[self]

    @classmethod
    def de_etiqueta(cls, etiqueta: str) -> Gravedad:
        return {"baja": cls.BAJA, "media": cls.MEDIA, "alta": cls.ALTA}[etiqueta]


@dataclass(frozen=True, slots=True)
class Marca:
    """Una señal en la vacante: qué regla, qué frase, qué tan grave y qué corregir."""

    regla: str
    senal: str
    gravedad: Gravedad
    cita: str | None = None
    corregir: str | None = None

    def a_json(self) -> dict[str, str | None]:
        """La forma de `vacantes.motivos_moderacion` (0019) que lee el panel."""
        return {
            "regla": self.regla,
            "cita": self.cita,
            "senal": self.senal,
            "gravedad": self.gravedad.etiqueta,
            "corregir": self.corregir,
        }

    @classmethod
    def de_json(cls, datos: dict[str, str | None]) -> Marca:
        return cls(
            regla=str(datos.get("regla") or ""),
            senal=str(datos.get("senal") or ""),
            gravedad=Gravedad.de_etiqueta(str(datos.get("gravedad") or "baja")),
            cita=datos.get("cita"),
            corregir=datos.get("corregir"),
        )


# ─────────────────────────────── texto plano ───────────────────────────────


def _plano_de(c: str) -> str:
    base = unicodedata.normalize("NFD", c)[:1].lower()[:1]
    return base or c


def plano(texto: str) -> str:
    """Minúsculas y sin acentos, carácter por carácter.

    Tiene el mismo largo que el original: lo que una regla encuentra en el texto
    plano se cita tal cual del original, con sus acentos y mayúsculas.
    """
    return "".join(_plano_de(c) for c in texto)


#: Lo más largo que se cita de una frase.
MAX_CITA = 140


def _citar(original: str, inicio: int, fin: int) -> str:
    cita = " ".join(original[inicio:fin].split())
    return cita if len(cita) <= MAX_CITA else cita[: MAX_CITA - 1].rstrip() + "…"


# ─────────────────────────────── reglas fijas ───────────────────────────────


@dataclass(frozen=True, slots=True)
class _Regla:
    nombre: str
    gravedad: Gravedad
    senal: str
    corregir: str
    patrones: tuple[re.Pattern[str], ...]


def _r(*patrones: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p) for p in patrones)


#: Dominio que no va pegado a una letra, número o punto anterior.
_DOM = r"(?<![\w.])"

REGLAS: tuple[_Regla, ...] = (
    _Regla(
        nombre="pago",
        gravedad=Gravedad.ALTA,
        senal="Le pide al candidato pagar, depositar o comprar algo (curso, kit, inscripción).",
        corregir=(
            "Quita cualquier cobro al candidato. En Vector HR una vacante no pide pagos, "
            "depósitos, cursos ni kits."
        ),
        patrones=_r(
            r"\b(debes|deberas|tendras que|tienes que|hay que|se requiere|requieres?|necesitas"
            r"|es necesario)\s+(pagar|depositar|abonar|transferir|comprar|adquirir|invertir)\b",
            r"\b(cuota|costo|pago|deposito|cobro)\s+(unic[oa]\s+)?(de|por)\s+(la\s+|el\s+|tu\s+)?"
            r"(inscripcion|registro|capacitacion|curso|kit|materiales?|uniforme|afiliacion"
            r"|garantia|apertura|alta|examen|certificacion|tramite)\b",
            r"\b(compra|comprar|adquiere|adquirir|paga|pagar)\s+(tu|el|un|su|la)\s+"
            r"(kit|curso|paquete|membresia)\b",
            r"\bkit\s+de\s+(inicio|arranque)\b",
        ),
    ),
    _Regla(
        nombre="datos_bancarios",
        gravedad=Gravedad.ALTA,
        senal="Pide datos bancarios o de la tarjeta del candidato.",
        corregir=(
            "No pidas datos bancarios en la vacante. Los datos de nómina se piden al "
            "contratar, nunca para postularse."
        ),
        patrones=_r(
            r"\b(numero|num\.?|no\.)\s+de\s+(cuenta|tarjeta)\b",
            r"\b(datos|informacion)\s+(bancari[oa]s|de\s+tu\s+(cuenta|tarjeta|banco))\b",
            r"\bclabe\b",
            r"\b(cvv|cvc|nip|pin)\s+(de\s+)?(tu\s+)?(tarjeta|cuenta|banco)\b",
            r"\bcodigo\s+de\s+seguridad\s+de\s+(tu\s+)?tarjeta\b",
            r"\b(usuario|clave|contrasena)\s+de\s+(tu\s+)?(banca|banco)\b",
        ),
    ),
    _Regla(
        nombre="documentos_antes",
        gravedad=Gravedad.MEDIA,
        senal="Pide documentos de identidad antes de la entrevista.",
        corregir=(
            "Pide la identificación al contratar, no antes de la entrevista. Para postularse "
            "basta el CV."
        ),
        patrones=_r(
            r"\b(envia|enviar|envianos|manda|mandar|mandanos|adjunta|adjuntar|comparte)\b"
            r"[^.\n]{0,60}\b(ine|ife|cedula|pasaporte|rif|curp|rfc|acta\s+de\s+nacimiento"
            r"|identificacion|comprobante\s+de\s+domicilio|selfie)\b[^.\n]{0,80}"
            r"(antes\s+de\s+(la|tu)\s+entrevista|para\s+(agendar|reservar|apartar|asegurar"
            r"|confirmar)\s+(tu|la|el)\s+(entrevista|vacante|lugar|puesto|cita))",
            r"\bantes\s+de\s+(la|tu)\s+entrevista\b[^.\n]{0,60}\b(ine|ife|cedula|pasaporte"
            r"|curp|rfc|rif|identificacion|documentos)\b",
        ),
    ),
    _Regla(
        nombre="contacto_externo",
        gravedad=Gravedad.MEDIA,
        senal=(
            "Manda a contactar por WhatsApp o Telegram, o trae un enlace acortado. En el "
            "career site se aplica con el formulario."
        ),
        corregir=(
            "Quita los WhatsApp, Telegram y enlaces acortados: los candidatos aplican con el "
            "formulario y te llegan al panel."
        ),
        patrones=_r(
            r"\b(whats?app|wasap|whatsap|watsap|telegram)\b",
            _DOM + r"(wa\.me|t\.me|api\.whatsapp\.com|chat\.whatsapp\.com)/",
            _DOM + r"(bit\.ly|tinyurl\.com|goo\.gl|ow\.ly|is\.gd|cutt\.ly|rebrand\.ly"
            r"|shorturl\.at|rb\.gy|t\.ly|acortar\.link|wa\.link|linktr\.ee|tiny\.cc|s\.id)/",
        ),
    ),
    _Regla(
        nombre="multinivel",
        gravedad=Gravedad.ALTA,
        senal="Es multinivel o pide una inversión para empezar.",
        corregir=(
            "El career site es para empleos. Los esquemas multinivel y lo que pide invertir "
            "no se publican."
        ),
        patrones=_r(
            r"\b(multinivel|mlm|network\s+marketing|marketing\s+de\s+redes|red\s+de\s+mercadeo"
            r"|esquema\s+piramidal|sistema\s+piramidal)\b",
            r"\b(inversion|aportacion|aporte)\s+(minima|inicial|de\s+entrada)\b",
            r"\brecuperas?\s+tu\s+inversion\b",
            r"\b(invierte|invertir)\s+(desde\s+|solo\s+)?\$\s?\d",
        ),
    ),
    _Regla(
        nombre="inversion_o_cripto",
        gravedad=Gravedad.MEDIA,
        senal='Habla de cripto, trading o "ser tu propio jefe".',
        corregir=(
            "Describe el puesto, sus tareas y su pago. Las promesas de independencia financiera "
            "o de trading no son una vacante."
        ),
        patrones=_r(
            r"\b(cripto(monedas?|activos)?|bitcoin|usdt|forex|opciones\s+binarias|trading)\b",
            r"\bse\s+tu\s+propio\s+jefe\b",
            r"\b(libertad|independencia)\s+financiera\b",
        ),
    ),
)

# El sueldo irreal no es una frase sino una combinación: una promesa de ganancia
# junto con "sin experiencia" y "desde casa". Una vacante de ventas con comisiones
# y "ingresos de hasta $X" no cae si pide experiencia o es presencial.
_PROMESA = _r(
    r"\b(gana[rs]?|ingresos?|generar?)\s+(de\s+|desde\s+)?(hasta|mas\s+de|arriba\s+de)\s+\$?\s?\d",
    r"\b(gana[rs]?)\s+\$\s?\d",
    r"\bingresos?\s+(ilimitados?|sin\s+limite)\b",
    r"\$\s?\d[\d.,]*\s*(diarios|al\s+dia|por\s+dia|semanales|a\s+la\s+semana)\b",
)
_SIN_EXPERIENCIA = _r(
    r"\bsin\s+experiencia\b",
    r"\bno\s+(se\s+)?(requiere|requieres|necesitas|es\s+necesaria)\s+(de\s+)?experiencia\b",
)
_DESDE_CASA = _r(
    r"\bdesde\s+(tu\s+|la\s+)?(casa|celular|telefono|movil|hogar)\b",
    r"\bhome\s*office\b",
    r"\b100\s*%\s*remoto\b",
    r"\ben\s+tus\s+tiempos\s+libres\b",
)
_DINERO_FACIL = _r(r"\bdinero\s+(facil|rapido)\b")

REGLA_SUELDO_IRREAL = _Regla(
    nombre="sueldo_irreal",
    gravedad=Gravedad.MEDIA,
    senal='Promete ganancias altas "sin experiencia" y "desde casa", o "dinero fácil".',
    corregir=(
        "Pon el sueldo real del puesto y lo que se pide para hacerlo. Las promesas de ganar "
        "mucho sin experiencia hacen que la vacante parezca falsa."
    ),
    patrones=(),
)


def _primera(patrones: Sequence[re.Pattern[str]], texto: str) -> re.Match[str] | None:
    hallados = [m for p in patrones if (m := p.search(texto))]
    return min(hallados, key=lambda m: m.start()) if hallados else None


def revisar_texto(titulo: str, descripcion: str) -> list[Marca]:
    """Las marcas de las reglas fijas sobre lo que el candidato lee. Una por regla."""
    original = f"{titulo}\n{descripcion}"
    texto = plano(original)
    marcas: list[Marca] = []
    for regla in REGLAS:
        if m := _primera(regla.patrones, texto):
            marcas.append(
                Marca(
                    regla=regla.nombre,
                    senal=regla.senal,
                    gravedad=regla.gravedad,
                    cita=_citar(original, m.start(), m.end()),
                    corregir=regla.corregir,
                )
            )

    facil = _primera(_DINERO_FACIL, texto)
    promesa = _primera(_PROMESA, texto)
    combinada = (
        promesa
        if promesa and _primera(_SIN_EXPERIENCIA, texto) and _primera(_DESDE_CASA, texto)
        else None
    )
    if m := facil or combinada:
        marcas.append(
            Marca(
                regla=REGLA_SUELDO_IRREAL.nombre,
                senal=REGLA_SUELDO_IRREAL.senal,
                gravedad=REGLA_SUELDO_IRREAL.gravedad,
                cita=_citar(original, m.start(), m.end()),
                corregir=REGLA_SUELDO_IRREAL.corregir,
            )
        )
    return marcas


# ─────────────────────────────── contexto ───────────────────────────────

#: Una cuenta con menos días que esto es nueva para la regla de ráfaga.
DIAS_DE_CUENTA_NUEVA = 7
#: Vacantes creadas en la última hora a partir de las cuales una cuenta nueva es ráfaga.
RAFAGA_MINIMA = 4

MOTIVO_RECLUTADOR = Marca(
    regla="reclutador_independiente",
    senal="Las vacantes de reclutadores independientes las revisa Vector HR antes de publicarlas.",
    gravedad=Gravedad.BAJA,
)
MOTIVO_PRIMERA_VACANTE = Marca(
    regla="primera_vacante",
    senal=(
        "La primera vacante de una empresa sin verificar la revisa Vector HR antes de "
        "publicarla. Las siguientes se publican solas si no tienen señales de riesgo."
    ),
    gravedad=Gravedad.BAJA,
)


@dataclass(frozen=True, slots=True)
class VacanteAModerar:
    """Una vacante 'pendiente' con lo que la decisión necesita de su empresa."""

    id: UUID
    empresa_id: UUID
    titulo: str
    descripcion: str
    empresa_verificada: bool
    publica_para: str
    #: La empresa ya tiene otra vacante publicada (abierta o cerrada).
    tiene_publicadas: bool
    #: El mismo texto lo publicó otra empresa.
    duplicada: bool
    #: Vacantes de la empresa creadas en la última hora, esta incluida.
    creadas_en_la_ultima_hora: int
    #: La empresa se creó hace menos de `DIAS_DE_CUENTA_NUEVA` días.
    cuenta_nueva: bool


def marcas_del_contexto(v: VacanteAModerar) -> list[Marca]:
    marcas: list[Marca] = []
    if v.duplicada:
        marcas.append(
            Marca(
                regla="duplicada",
                senal="El mismo texto ya lo publicó otra cuenta.",
                gravedad=Gravedad.MEDIA,
                corregir="Describe la vacante con tus propias palabras.",
            )
        )
    if v.cuenta_nueva and v.creadas_en_la_ultima_hora >= RAFAGA_MINIMA:
        marcas.append(
            Marca(
                regla="rafaga",
                senal=(
                    f"Una cuenta nueva creó {v.creadas_en_la_ultima_hora} vacantes en menos de "
                    "una hora."
                ),
                gravedad=Gravedad.MEDIA,
            )
        )
    return marcas


def evaluar(v: VacanteAModerar, extra: Sequence[Marca] = ()) -> list[Marca]:
    """Todas las marcas: las reglas fijas, el contexto y las de un revisor externo (PR 3)."""
    return [*revisar_texto(v.titulo, v.descripcion), *marcas_del_contexto(v), *extra]


# ─────────────────────────────── decisión ───────────────────────────────


@dataclass(frozen=True, slots=True)
class Decision:
    estado: EstadoDeModeracion
    riesgo: Gravedad
    motivos: tuple[Marca, ...]


def decidir(v: VacanteAModerar, marcas: Sequence[Marca]) -> Decision:
    """A dónde va la vacante, de lo más grave a lo menos.

    1. Riesgo alto: se rechaza y la empresa ve qué corregir.
    2. Reclutador independiente: siempre a revisión.
    3. Primera vacante de una empresa sin verificar: a revisión.
    4. Riesgo medio: a revisión.
    5. Lo demás se publica.
    """
    riesgo = max((m.gravedad for m in marcas), default=Gravedad.BAJA)
    senales = sorted((m for m in marcas if m.gravedad >= Gravedad.MEDIA), key=lambda m: -m.gravedad)
    if riesgo is Gravedad.ALTA:
        return Decision(EstadoDeModeracion.RECHAZADA, riesgo, tuple(senales))

    motivos = list(senales)
    if v.publica_para == "clientes":
        motivos.append(MOTIVO_RECLUTADOR)
    elif not v.empresa_verificada and not v.tiene_publicadas:
        motivos.append(MOTIVO_PRIMERA_VACANTE)
    if motivos:
        return Decision(EstadoDeModeracion.EN_REVISION, riesgo, tuple(motivos))
    return Decision(EstadoDeModeracion.PUBLICADA, riesgo, ())


# ─────────────────────────────── insignia ───────────────────────────────

#: Correos que cualquiera abre gratis: con ellos el dominio no prueba nada.
PROVEEDORES_GRATUITOS = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "hotmail.com",
        "hotmail.es",
        "hotmail.co.uk",
        "outlook.com",
        "outlook.es",
        "live.com",
        "live.com.mx",
        "msn.com",
        "yahoo.com",
        "yahoo.com.mx",
        "yahoo.es",
        "ymail.com",
        "rocketmail.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "proton.me",
        "protonmail.com",
        "pm.me",
        "aol.com",
        "gmx.com",
        "gmx.net",
        "gmx.es",
        "zoho.com",
        "zohomail.com",
        "yandex.com",
        "yandex.ru",
        "mail.com",
        "tutanota.com",
        "tuta.io",
        "fastmail.com",
        "hey.com",
        # México y Venezuela: correos de los proveedores de internet.
        "prodigy.net.mx",
        "infinitummail.com",
        "telmex.com",
        "cantv.net",
        "movistar.net.ve",
    }
)

#: Segundos niveles donde el dominio registrable lleva tres partes (empresa.com.mx).
#: No hay Public Suffix List en las dependencias (ni hace falta para MX y VE): esta
#: lista, más la regla de `_SLD_GENERICOS` para cualquier país de dos letras, cubre
#: Latinoamérica. Ante la duda se niega la insignia: un sufijo público nunca cuenta
#: como dominio de una empresa.
SEGUNDOS_NIVELES = frozenset(
    {
        "com.mx", "org.mx", "net.mx", "edu.mx", "gob.mx",
        "com.ve", "org.ve", "net.ve", "co.ve", "edu.ve", "gob.ve", "web.ve",
        "com.co", "org.co", "net.co", "edu.co", "gov.co",
        "com.ar", "com.pe", "com.br", "com.ec", "com.gt", "com.pa", "com.do",
        "com.uy", "com.py", "com.bo", "com.sv", "com.hn", "com.ni", "co.cr", "com.cu",
        "com.es", "co.uk", "org.uk",
    }
)  # fmt: skip
#: `com.xx`, `org.xx`… bajo un país de dos letras son sufijos públicos aunque no estén
#: en la lista (com.au, org.nz).
_SLD_GENERICOS = frozenset(
    {"com", "org", "net", "edu", "gob", "gov", "co", "ac", "web", "nom", "mil", "int"}
)


def _es_sufijo_publico(dos_partes: list[str]) -> bool:
    sld, tld = dos_partes
    return f"{sld}.{tld}" in SEGUNDOS_NIVELES or (len(tld) == 2 and sld in _SLD_GENERICOS)


def dominio_registrable(host: str) -> str | None:
    """`rh.empresa.com.mx` → `empresa.com.mx`. Sin dominio válido, `None`."""
    host = host.strip().lower().rstrip(".")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", host):
        return None
    partes = host.split(".")
    if all(p.isdigit() for p in partes):
        return None
    if _es_sufijo_publico(partes[-2:]):
        return ".".join(partes[-3:]) if len(partes) >= 3 else None
    return ".".join(partes[-2:])


def _host_de_la_web(web: str) -> str | None:
    url = web.strip()
    if "://" not in url:
        url = "https://" + url
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def insignia_por_dominio(correo: str, web: str | None, publica_para: str) -> bool:
    """La insignia "Empresa verificada" que se gana sola, al confirmar el código.

    Solo si publica para su propia empresa, el correo no es de un proveedor
    gratuito y el dominio registrable del correo es el de su web: `rh@empresa.com.mx`
    con `https://www.empresa.com.mx` sí; con Gmail o con otra web, no. El código de
    acceso ya probó que la persona lee ese correo.
    """
    if publica_para != "propia" or not web or correo.count("@") != 1:
        return False
    dominio_del_correo = correo.rsplit("@", 1)[1].strip().lower()
    del_correo = dominio_registrable(dominio_del_correo)
    host = _host_de_la_web(web)
    de_la_web = dominio_registrable(host) if host else None
    if not del_correo or not de_la_web:
        return False
    if dominio_del_correo in PROVEEDORES_GRATUITOS or del_correo in PROVEEDORES_GRATUITOS:
        return False
    return del_correo == de_la_web


# ─────────────────────────────── puertos ───────────────────────────────


@dataclass(frozen=True, slots=True)
class VacanteEnCola:
    """Una vacante que espera a una persona de Vector HR, como la ve el resumen."""

    id: UUID
    titulo: str
    descripcion: str
    empresa: str
    empresa_verificada: bool
    publica_para: str
    estado: EstadoDeModeracion
    motivos: tuple[Marca, ...]


@dataclass(frozen=True, slots=True)
class AvisosRecientes:
    ultimo: datetime | None
    ultimas_24_horas: int


class RepositorioDeModeracion(Protocol):
    async def pendientes(self, lote: int) -> list[VacanteAModerar]:
        """Vacantes abiertas en 'pendiente', bloqueadas para este barrido."""
        ...

    async def guardar(self, vacante_id: UUID, decision: Decision) -> bool:
        """Guarda la decisión si la vacante sigue 'pendiente'."""
        ...

    async def cola_sin_avisar(self, limite: int) -> list[VacanteEnCola]: ...

    async def vacante_en_cola(self, vacante_id: UUID) -> VacanteEnCola | None:
        """La vacante para la página de revisión, en el estado que esté."""
        ...

    async def marcar_avisadas(self, ids: Sequence[UUID]) -> None: ...

    async def avisos_recientes(self) -> AvisosRecientes: ...

    async def registrar_aviso(self, *, urgente: bool, vacantes: int) -> None: ...

    async def resolver(
        self,
        vacante_id: UUID,
        estado: EstadoDeModeracion,
        motivo: Marca | None,
        desde: Sequence[EstadoDeModeracion],
    ) -> bool:
        """Cambia el estado si la vacante está en uno de `desde`."""
        ...

    async def guardar_verificacion(
        self,
        empresa_id: UUID,
        *,
        publica_para: str,
        web: str | None,
        linkedin: str | None,
        verificada: bool,
    ) -> bool:
        """Guarda cómo publica y suma la insignia; nunca la quita sola. Devuelve si la tiene."""
        ...


@dataclass(frozen=True, slots=True)
class AltaConfirmada:
    """Un alta desde la web (`privado.altas_web`) cuyo dueño ya escribió el código."""

    alta_id: int
    empresa_id: UUID
    #: El correo que confirmó: el código de acceso probó que la persona lo lee.
    correo: str
    publica_para: str
    web: str | None
    linkedin: str | None
    confirmado_en: datetime


class RepositorioDeConfirmaciones(Protocol):
    """Las altas desde la web que confirmaron el código y todavía no tienen la marca."""

    async def confirmadas_sin_marcar(self, limite: int) -> list[AltaConfirmada]: ...

    async def marcar_confirmada(self, alta_id: int, confirmado_en: datetime) -> None:
        """Pone `confirmado_en`, la marca que también lee la limpieza de 7 días."""
        ...


class RevisorDeVacantes(Protocol):
    """Un revisor externo (el modelo del PR 3). Devuelve marcas como las reglas."""

    async def revisar(self, vacante: VacanteAModerar) -> Sequence[Marca]: ...


class ServicioDeCorreo(Protocol):
    async def enviar(self, *, para: str, asunto: str, texto: str) -> None: ...
