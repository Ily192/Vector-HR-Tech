"""FastAPI app · hr-engine."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import cv_evaluator, health, sourcer
from app.config import settings
from app.monitoring import init_monitoring, logger


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_monitoring()
    logger.info(
        "hr-engine starting",
        version=settings.service_version,
        env=settings.env,
    )
    yield
    logger.info("hr-engine shutting down")


app = FastAPI(
    title="Vortex Ops · HR Engine",
    version=settings.service_version,
    description="HR execution engine: workers, scoring, pipeline.",
    lifespan=lifespan,
    docs_url="/docs" if settings.env != "production" else None,
    redoc_url=None,
)

# CORS — restringir en prod via env
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)

# ── Routers ──
app.include_router(health.router)
app.include_router(sourcer.router, prefix="/api/sourcer", tags=["sourcer"])
app.include_router(cv_evaluator.router, prefix="/api/cv-evaluator", tags=["cv-evaluator"])
