"""Logs estructurados + Sentry + OpenTelemetry init.

`init_monitoring()` es idempotente y se llama desde:
- el lifespan de FastAPI (`app.main`)
- el import del Celery app (`app.workers.celery_app`)

Nota histórica: structlog estaba configurado con `structlog.stdlib.*` processors
pero SIN `logger_factory`, así que caía al `PrintLoggerFactory` por defecto y
`add_logger_name` reventaba con `AttributeError: 'PrintLogger' object has no
attribute 'name'` en la PRIMERA línea de log (tiraba el lifespan y el worker).
El `logger_factory=structlog.stdlib.LoggerFactory()` de abajo es obligatorio
para que el stack `structlog.stdlib` funcione y para que `logging.basicConfig`
/ `settings.log_level` controlen de verdad el nivel.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

import sentry_sdk
import structlog
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.config import settings

if TYPE_CHECKING:  # pragma: no cover - solo para tipos
    from fastapi import FastAPI

_initialized = False


def init_monitoring(*, force: bool = False) -> None:
    """Llamar una vez al startup del proceso (api o worker). Idempotente."""
    global _initialized
    if _initialized and not force:
        return
    _init_logging()
    _init_sentry()
    _init_otel()
    _initialized = True


def _log_level_int() -> int:
    level = logging.getLevelName(settings.log_level.upper())
    return level if isinstance(level, int) else logging.INFO


def _init_logging() -> None:
    level = _log_level_int()
    # `force=True`: uvicorn/celery pueden haber tocado el root logger antes que
    # nosotros; sin esto `basicConfig` es un no-op y `LOG_LEVEL` se ignora.
    logging.basicConfig(level=level, format="%(message)s", force=True)
    logging.getLogger().setLevel(level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        # ── El fix: sin esto structlog usa PrintLoggerFactory y los
        #    processors `structlog.stdlib.*` explotan.
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def _init_sentry() -> None:
    if not settings.sentry_dsn or settings.env == "development":
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        release=f"{settings.service_name}@{settings.service_version}",
        traces_sample_rate=0.1 if settings.env == "production" else 1.0,
        profiles_sample_rate=0.1,
        send_default_pii=False,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
    )


def _otel_headers() -> dict[str, str]:
    """Parsea `OTEL_EXPORTER_OTLP_HEADERS` (formato W3C: k=v,k2=v2)."""
    raw = settings.otel_exporter_otlp_headers.strip()
    if not raw:
        return {}
    headers: dict[str, str] = {}
    for chunk in raw.split(","):
        if "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        headers[key.strip()] = value.strip()
    return headers


def _init_otel() -> None:
    """Traces OTLP/HTTP. No-op si `OTEL_EXPORTER_OTLP_ENDPOINT` está vacío.

    Decisión (ver informe): mantenemos las dependencias `opentelemetry-*` y las
    inicializamos de verdad en vez de borrarlas, porque el tracing distribuido
    API → Celery → Postgres es el único modo de atribuir costo y latencia por
    run entre procesos. Sin endpoint configurado no se instala ningún provider,
    así que en dev/test el costo es cero.
    """
    endpoint = settings.otel_exporter_otlp_endpoint.strip()
    if not endpoint:
        return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": settings.service_version,
            "deployment.environment": settings.env,
        },
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=endpoint, headers=_otel_headers()),
        ),
    )
    trace.set_tracer_provider(provider)
    SQLAlchemyInstrumentor().instrument()
    # El paquete de instrumentación de Celery no publica tipos completos.
    CeleryInstrumentor().instrument()  # type: ignore[no-untyped-call]
    logger.info("otel.initialized", endpoint=endpoint)


def instrument_fastapi(app: FastAPI) -> None:
    """Instrumenta la app FastAPI si OTel está configurado."""
    if not settings.otel_exporter_otlp_endpoint.strip():
        return
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,ready")


def hash_pii(value: str | None, *, length: int = 12) -> str | None:
    """Hash corto y estable de un dato personal, apto para logs.

    Permite correlacionar líneas de log del mismo candidato sin escribir su
    nombre (ni su CV) en el log agregado. El `jwt_secret` actúa como sal, así
    que el hash no es reversible por diccionario desde fuera del deploy.
    """
    if not value:
        return None
    digest = hashlib.sha256(f"{settings.jwt_secret}:{value}".encode()).hexdigest()
    return digest[:length]


def bind_log_context(**kwargs: Any) -> None:
    """Bindea contexto (request_id, empresa_id, run_id) a todos los logs del task."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_log_context() -> None:
    structlog.contextvars.clear_contextvars()


logger: structlog.stdlib.BoundLogger = structlog.get_logger("hr-engine")
