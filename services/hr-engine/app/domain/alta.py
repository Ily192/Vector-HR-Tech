"""Alta de una empresa en el plan gratis: Vector HR la crea y la invita (ADR-017).

Las reglas que no dependen de la base: cómo se escriben el correo, el nombre y el
slug, y cómo se guarda el token de la invitación. El token viaja en el correo y
en el metadata del signup; la base guarda solo su hash, que `handle_new_user`
(0003) compara con `encode(sha256(invite_token::bytea), 'hex')`.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata
from dataclasses import dataclass
from typing import Literal, cast, get_args

RolDeAlta = Literal["HR", "Director"]

#: El mismo tope que el puesto de una vacante: un nombre, no un párrafo.
MAX_LARGO_DEL_NOMBRE = 120
#: Base del slug, antes del sufijo que lo desempata.
MAX_LARGO_DEL_SLUG = 50

_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SolicitudInvalidaError(ValueError):
    """Faltan datos de la empresa o de la persona, o vienen mal escritos."""


@dataclass(frozen=True)
class SolicitudDeAlta:
    """Quién se da de alta: la empresa y la persona de HR o Dirección que la usará.

    Se crea con `nueva()`, que normaliza y valida; el plan es siempre el gratis.
    """

    empresa: str
    correo: str
    nombre: str
    tamano: int | None = None
    rol: RolDeAlta = "HR"

    @classmethod
    def nueva(
        cls,
        *,
        empresa: str,
        correo: str,
        nombre: str,
        tamano: int | None = None,
        rol: str = "HR",
    ) -> SolicitudDeAlta:
        empresa = " ".join(empresa.split())
        nombre = " ".join(nombre.split())
        correo = correo.strip().lower()
        if not 1 <= len(empresa) <= MAX_LARGO_DEL_NOMBRE:
            raise SolicitudInvalidaError(
                f"el nombre de la empresa lleva de 1 a {MAX_LARGO_DEL_NOMBRE} caracteres"
            )
        if not 1 <= len(nombre) <= MAX_LARGO_DEL_NOMBRE:
            raise SolicitudInvalidaError(
                f"el nombre de la persona lleva de 1 a {MAX_LARGO_DEL_NOMBRE} caracteres"
            )
        if not _CORREO.match(correo):
            raise SolicitudInvalidaError(f"el correo no es válido: {correo!r}")
        if tamano is not None and tamano < 1:
            raise SolicitudInvalidaError("el tamaño es el número de personas, de 1 en adelante")
        if rol not in get_args(RolDeAlta):
            raise SolicitudInvalidaError(f"el rol es HR o Director, no {rol!r}")
        return cls(
            empresa=empresa, correo=correo, nombre=nombre, tamano=tamano, rol=cast(RolDeAlta, rol)
        )


def slug_de_empresa(nombre: str, sufijo: str | None = None) -> str:
    """ "Ferretería Norte" → "ferreteria-norte". Con `sufijo`, "ferreteria-norte-3f9a".

    El slug de la empresa es único (0001): si ya existe, se reintenta con sufijo.
    """
    ascii_ = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", ascii_.lower())[:MAX_LARGO_DEL_SLUG].strip("-")
    partes = [p for p in (base, sufijo) if p]
    return "-".join(partes) or secrets.token_hex(2)


def nuevo_token() -> str:
    """El token de un solo uso de la invitación. Solo con caracteres de URL."""
    return secrets.token_urlsafe(32)


def hash_del_token(token: str) -> str:
    """El hash que guarda `invitations.token_hash`; el token en claro no se guarda."""
    return hashlib.sha256(token.encode()).hexdigest()
