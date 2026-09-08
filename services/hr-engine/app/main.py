"""FastAPI app · hr-engine."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import cv_evaluator, health, sourcer
from app.api.rate_limit import limiter
from app.config import settings
from app.monitoring import (
    bind_log_context,
    clear_log_context,
    init_monitoring,
    instrument_fastapi,
    logger,
)

REQUEST_ID_HEADER = "X-Request-ID"

#: Disponible para los exception handlers, que corren fuera del middleware.
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_monitoring()
    logger.info(
        "hr-engine starting",
        version=settings.service_version,
        env=settings.env,
        log_level=settings.log_level,
    )
    yield
    logger.info("hr-engine shutting down")


# `init_monitoring()` también acá: los exception handlers y el import de los
# routers pueden loguear antes de que arranque el lifespan.
init_monitoring()

app = FastAPI(
    title="Vortex Ops · HR Engine",
    version=settings.service_version,
    description=(
        "HR execution engine: workers, scoring, pipeline.\n\n"
        "Los endpoints `/api/*/run` requieren un **run-token** JWT emitido por "
        "Paperclip (ADR-005) en `Authorization: Bearer <token>`. El "
        "`empresa_id`, el `run_id` y el `cost_cap_usd` se toman del token, "
        "nunca del body."
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.env != "production" else None,
    redoc_url=None,
)

# ── Rate limiting (slowapi) ──
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# ── CORS — configurable por env (CORS_ALLOW_ORIGINS, CSV) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
    expose_headers=[REQUEST_ID_HEADER],
)


@app.middleware("http")
async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Correlación: request-id propagado a logs, respuesta y Celery."""
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    request.state.request_id = request_id
    token = _request_id_ctx.set(request_id)
    clear_log_context()
    bind_log_context(request_id=request_id, path=request.url.path, method=request.method)
    try:
        response = await call_next(request)
    finally:
        clear_log_context()
        _request_id_ctx.reset(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def _current_request_id(request: Request) -> str:
    rid = getattr(request.state, "request_id", None)
    return str(rid) if rid else _request_id_ctx.get()


def _error_response(
    request: Request,
    *,
    status_code: int,
    detail: object,
    error: str,
) -> JSONResponse:
    request_id = _current_request_id(request)
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "detail": detail, "request_id": request_id},
        headers={REQUEST_ID_HEADER: request_id},
    )


async def http_exception_handler(request: Request, exc: Exception) -> Response:
    """HTTPException con request-id + headers (WWW-Authenticate del 401)."""
    assert isinstance(exc, StarletteHTTPException)
    response = _error_response(
        request,
        status_code=exc.status_code,
        detail=exc.detail,
        error="http_error",
    )
    for key, value in (exc.headers or {}).items():
        response.headers[key] = value
    return response


async def validation_exception_handler(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)
    return _error_response(
        request,
        status_code=422,  # nombre de la constante cambió entre versiones de Starlette
        detail=exc.errors(),
        error="validation_error",
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    """Último recurso: 500 con request-id en vez de un traceback anónimo."""
    logger.error(
        "unhandled_exception",
        request_id=_current_request_id(request),
        path=request.url.path,
        method=request.method,
        error_type=type(exc).__name__,
        exc_info=exc,
    )
    return _error_response(
        request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error",
        error="internal_error",
    )


async def rate_limit_handler(request: Request, exc: Exception) -> Response:
    limit = getattr(exc, "detail", "rate limit exceeded")
    logger.warning("rate_limit.exceeded", path=request.url.path, limit=str(limit))
    return _error_response(
        request,
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Rate limit excedido: {limit}",
        error="rate_limited",
    )


app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ── Routers ──
app.include_router(health.router)
app.include_router(sourcer.router, prefix="/api/sourcer", tags=["sourcer"])
app.include_router(cv_evaluator.router, prefix="/api/cv-evaluator", tags=["cv-evaluator"])

instrument_fastapi(app)
