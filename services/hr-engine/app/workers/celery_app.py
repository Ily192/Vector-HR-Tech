"""Celery app — broker + backend, registra todos los workers."""

from celery import Celery
from celery.signals import worker_ready

from app.config import settings
from app.monitoring import init_monitoring, logger

init_monitoring()

celery_app = Celery(
    "vortex_hr",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.sourcer",
        "app.workers.cv_evaluator",
        # próximas etapas:
        # "app.workers.psicometrico",
        # "app.workers.interviewer",
        # "app.workers.scheduler",
        # "app.workers.onboarder",
        # "app.workers.compliance",
        # "app.workers.pipeline",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_pool="prefork",
    worker_concurrency=settings.celery_concurrency,
    task_default_queue="hr",
    task_reject_on_worker_lost=True,
    # ── Timeouts ──────────────────────────────────────────────────────────
    # Sin esto una task colgada en un LLM retiene un slot del worker para
    # siempre. Soft = excepción dentro de la task (permite cleanup);
    # hard = SIGKILL al proceso hijo.
    task_time_limit=settings.celery_task_time_limit,
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    # TTL de resultados en Redis: sin esto crecen sin límite.
    result_expires=settings.celery_result_expires,
    broker_transport_options={
        # Debe ser > task_time_limit; si no, Redis re-entrega la task mientras
        # todavía está corriendo (duplicando el gasto en LLMs).
        "visibility_timeout": settings.celery_visibility_timeout,
    },
    result_backend_transport_options={
        "visibility_timeout": settings.celery_visibility_timeout,
    },
    # ── Rate limit ────────────────────────────────────────────────────────
    # Techo por worker sobre TODAS las tasks: acota el gasto LLM aunque la
    # cola venga llena.
    task_default_rate_limit=settings.celery_task_default_rate_limit,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        # placeholder: cycle 1 agrega scheduler
    },
)


@worker_ready.connect
def _on_worker_ready(**_kwargs: object) -> None:
    logger.info(
        "celery worker ready",
        queue="hr",
        concurrency=settings.celery_concurrency,
        task_time_limit=settings.celery_task_time_limit,
    )
