"""Rate limiting (slowapi) — global por IP + por tenant en los endpoints /run.

Por qué: `POST /api/*/run` encola trabajo que gasta dinero en LLMs por request.
Aun con run-token válido, un tenant con un loop roto puede quemar el
presupuesto de toda la plataforma.

Dos capas:
1. `rate_limit_global` — middleware por IP sobre toda la app (defensa ante
   floods antes incluso de validar el token).
2. `rate_limit_tenant_runs` — decorador por endpoint, keyed por el `empresa_id`
   del run-token ya verificado.

En producción `RATE_LIMIT_STORAGE_URI` es obligatorio (ver `app.config`): el
storage en memoria no se comparte entre workers uvicorn y el límite real
terminaría siendo N veces el configurado.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings


def tenant_key(request: Request) -> str:
    """Key por tenant. Cae a la IP si todavía no hay token verificado."""
    empresa_id = getattr(request.state, "empresa_id", None)
    if empresa_id is not None:
        return f"tenant:{empresa_id}"
    return f"ip:{get_remote_address(request)}"


def _storage_uri() -> str:
    return settings.rate_limit_storage_uri or "memory://"


limiter = Limiter(
    key_func=tenant_key,
    default_limits=[settings.rate_limit_global],
    storage_uri=_storage_uri(),
    enabled=settings.rate_limit_enabled,
    headers_enabled=True,
)

#: Límite aplicado a los endpoints que encolan runs.
RUN_RATE_LIMIT = settings.rate_limit_tenant_runs
