"""Logs estructurados + Sentry + OpenTelemetry init."""

import logging

import sentry_sdk
import structlog
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.config import settings


def init_monitoring() -> None:
    """Llamar una vez al startup del proceso (api o worker)."""
    _init_logging()
    _init_sentry()


def _init_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(message)s",
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


logger: structlog.stdlib.BoundLogger = structlog.get_logger()
