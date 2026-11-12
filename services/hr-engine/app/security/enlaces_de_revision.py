"""Enlaces firmados de la cola de revisión (ADR-022).

El resumen que llega a hola@ trae, por vacante, un enlace a la página de
revisión del hr-engine. Quien lo tenga puede aprobarla o rechazarla, así que el
enlace se firma con HMAC-SHA256 (`MODERACION_SECRETO`, solo en el .env del VPS) y
vence. No hay sesión ni contraseña: el correo de Vector HR es el permiso.

Forma: `<vacante_id>.<vence_unix>.<firma_hex>`, sin base64, para que quepa entero
en una URL y se lea a simple vista.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from uuid import UUID

#: Lo que dura un enlace: una semana alcanza para revisar el resumen.
VIGENCIA_S = 7 * 24 * 3600


def _firma(secreto: str, vacante_id: UUID, vence: int) -> str:
    mensaje = f"moderacion.v1.{vacante_id}.{vence}".encode()
    return hmac.new(secreto.encode(), mensaje, hashlib.sha256).hexdigest()


def firmar(secreto: str, vacante_id: UUID, *, ahora: float | None = None) -> str:
    if not secreto:
        raise ValueError("MODERACION_SECRETO vacío: no se firman enlaces")
    vence = int(ahora if ahora is not None else time.time()) + VIGENCIA_S
    return f"{vacante_id}.{vence}.{_firma(secreto, vacante_id, vence)}"


def verificar(secreto: str, token: str, *, ahora: float | None = None) -> UUID | None:
    """La vacante del enlace, o `None` si la firma no cuadra, venció o no tiene forma."""
    if not secreto or len(token) > 200:
        return None
    partes = token.split(".")
    if len(partes) != 3:
        return None
    crudo_id, crudo_vence, firma = partes
    try:
        vacante_id = UUID(crudo_id)
        vence = int(crudo_vence)
    except ValueError:
        return None
    esperada = _firma(secreto, vacante_id, vence)
    if not hmac.compare_digest(esperada, firma):
        return None
    if vence < int(ahora if ahora is not None else time.time()):
        return None
    return vacante_id
