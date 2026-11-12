"""Alta desde vectorhrtech.com/publicar-vacantes: la empresa entra con un código.

La web guarda el registro en su base y llama al hr-engine de servidor a servidor
(`POST /alta/plan-gratis`). Aquí están las reglas que no dependen de la base ni de
Auth: qué valores se aceptan (los de `app/publicar-vacantes/opciones.ts` de la web),
cuántas vacantes da cada tamaño, cómo se guarda la IP y a qué página del panel
vuelve la persona a escribir su código.

La respuesta es la misma tenga o no cuenta el correo: desde afuera no se puede
saber quién usa el panel.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
from dataclasses import dataclass
from typing import Literal, get_args
from urllib.parse import quote, urlsplit

from app.domain.alta import SolicitudDeAlta, SolicitudInvalidaError

PublicaPara = Literal["propia", "clientes"]
Verificacion = Literal["dominio", "revision"]
Pais = Literal["mx", "ve", "otro"]
RangoDeTamano = Literal["1-15", "16-50", "51-200", "200+"]
Sector = Literal[
    "tecnologia",
    "comercio",
    "servicios",
    "contacto",
    "hospitalidad",
    "salud",
    "logistica",
    "industria",
    "educacion",
    "reclutamiento",
    "otro",
]
Contrataciones = Literal["0", "1-2", "3-5", "6+"]
Puesto = Literal[
    "tecnologia",
    "ventas",
    "diseno",
    "atencion",
    "administracion",
    "operativos",
    "salud",
    "otros",
]

#: Lo que la web manda como `lead_id` (el id de su fila en Neon): corto y sin espacios.
MAX_LARGO_DEL_LEAD = 64
#: Un cargo, no un párrafo.
MAX_LARGO_DEL_CARGO = 120
MAX_LARGO_DE_UNA_URL = 300
MAX_LARGO_DE_UN_UTM = 100
MAX_PUESTOS = len(get_args(Puesto))

#: El piso de cada rango: es lo que se guarda en `empresas.tamano_empleados`. Al plan
#: gratis solo le importa el corte de 51 personas (`domain/plan.py`), y el rango tal
#: cual queda en `altas_web.tamano`.
PISO_DEL_RANGO: dict[str, int] = {"1-15": 1, "16-50": 16, "51-200": 51, "200+": 200}


@dataclass(frozen=True)
class SolicitudDeAltaWeb:
    """El registro de la web, ya validado. `alta` es lo que crea la empresa."""

    lead_id: str
    alta: SolicitudDeAlta
    publica_para: PublicaPara
    cargo: str | None
    web_empresa: str | None
    linkedin: str | None
    verificacion: Verificacion
    pais: Pais
    tamano: RangoDeTamano | None
    sector: Sector
    contrataciones_mes: Contrataciones
    puestos: tuple[Puesto, ...]
    origen: str | None
    utm_medium: str | None
    utm_campaign: str | None
    ip: str | None

    @property
    def correo(self) -> str:
        return self.alta.correo

    @classmethod
    def nueva(
        cls,
        *,
        lead_id: str,
        nombre: str,
        correo: str,
        publica_para: str,
        empresa: str,
        cargo: str | None,
        web_empresa: str | None,
        linkedin: str | None,
        verificacion: str,
        pais: str,
        tamano: str | None,
        sector: str,
        contrataciones_mes: str,
        puestos: list[str] | tuple[str, ...],
        origen: str | None = None,
        utm_medium: str | None = None,
        utm_campaign: str | None = None,
        ip: str | None = None,
    ) -> SolicitudDeAltaWeb:
        lead_id = lead_id.strip()
        if not 1 <= len(lead_id) <= MAX_LARGO_DEL_LEAD or any(c.isspace() for c in lead_id):
            raise SolicitudInvalidaError("lead_id lleva de 1 a 64 caracteres, sin espacios")
        _opcion("publica_para", publica_para, PublicaPara)
        _opcion("verificacion", verificacion, Verificacion)
        _opcion("pais", pais, Pais)
        _opcion("sector", sector, Sector)
        _opcion("contrataciones_mes", contrataciones_mes, Contrataciones)
        if tamano is not None:
            _opcion("tamano", tamano, RangoDeTamano)
        for puesto in puestos:
            _opcion("puestos", puesto, Puesto)
        sin_repetir = tuple(dict.fromkeys(puestos))

        cargo = _texto_corto(cargo, MAX_LARGO_DEL_CARGO, "cargo")
        web_empresa = _url_https(web_empresa, "web_empresa")
        linkedin = _url_https(linkedin, "linkedin")
        if linkedin is not None and not _es_de_linkedin(linkedin):
            raise SolicitudInvalidaError("linkedin tiene que ser un perfil de linkedin.com")
        if publica_para == "clientes":
            # Reclutador independiente: su perfil personal es lo que se revisa.
            if linkedin is None or "/in/" not in urlsplit(linkedin).path:
                raise SolicitudInvalidaError(
                    "quien publica para empresas cliente da su LinkedIn personal (/in/)"
                )
        elif web_empresa is None and linkedin is None:
            raise SolicitudInvalidaError("la empresa da su sitio web o su LinkedIn")

        alta = SolicitudDeAlta.nueva(
            empresa=empresa,
            correo=correo,
            nombre=nombre,
            tamano=PISO_DEL_RANGO[tamano] if tamano is not None else None,
        )
        return cls(
            lead_id=lead_id,
            alta=alta,
            publica_para=publica_para,  # type: ignore[arg-type]
            cargo=cargo,
            web_empresa=web_empresa,
            linkedin=linkedin,
            verificacion=verificacion,  # type: ignore[arg-type]
            pais=pais,  # type: ignore[arg-type]
            tamano=tamano,  # type: ignore[arg-type]
            sector=sector,  # type: ignore[arg-type]
            contrataciones_mes=contrataciones_mes,  # type: ignore[arg-type]
            puestos=sin_repetir,  # type: ignore[arg-type]
            origen=_texto_corto(origen, MAX_LARGO_DE_UN_UTM, "origen"),
            utm_medium=_texto_corto(utm_medium, MAX_LARGO_DE_UN_UTM, "utm_medium"),
            utm_campaign=_texto_corto(utm_campaign, MAX_LARGO_DE_UN_UTM, "utm_campaign"),
            ip=ip_valida(ip),
        )


def _opcion(campo: str, valor: object, opciones: object) -> None:
    if valor not in get_args(opciones):
        raise SolicitudInvalidaError(f"{campo} no es una de las opciones del formulario")


def _texto_corto(valor: str | None, largo: int, campo: str) -> str | None:
    if valor is None:
        return None
    valor = " ".join(valor.split())
    if not valor:
        return None
    if len(valor) > largo:
        raise SolicitudInvalidaError(f"{campo} lleva hasta {largo} caracteres")
    return valor


def _url_https(valor: str | None, campo: str) -> str | None:
    """La web ya las normaliza a https; aquí solo se comprueba."""
    if valor is None or not valor.strip():
        return None
    valor = valor.strip()
    partes = urlsplit(valor)
    if (
        len(valor) > MAX_LARGO_DE_UNA_URL
        or partes.scheme != "https"
        or not partes.hostname
        or "." not in partes.hostname
        or any(c.isspace() for c in valor)
    ):
        raise SolicitudInvalidaError(f"{campo} tiene que ser una dirección https://")
    return valor


def _es_de_linkedin(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def ip_valida(ip: str | None) -> str | None:
    """La IP del visitante tal como la vio la web, o None si no es una IP."""
    if ip is None:
        return None
    try:
        return str(ipaddress.ip_address(ip.strip()))
    except ValueError:
        return None


def hash_de_ip(ip: str | None, clave: str) -> str | None:
    """La IP no se guarda: solo su HMAC, que sirve para el límite y para ver ráfagas."""
    if ip is None:
        return None
    return hmac.new(clave.encode(), ip.encode(), hashlib.sha256).hexdigest()


def url_de_verificacion(url_del_panel: str, correo: str) -> str:
    """La página del panel donde se escribe el código.

    El correo va en el fragmento (`#correo=`), que el navegador no manda a ningún
    servidor: no queda en los logs del panel ni en el Referer.
    """
    return f"{url_del_panel.rstrip('/')}/verificar#correo={quote(correo, safe='')}"
