"""Liveness + readiness."""

from fastapi import APIRouter
from sqlalchemy import text

from app.database import db_session

router = APIRouter()


@router.get("/health", tags=["health"])
async def liveness() -> dict[str, str]:
    """Liveness probe — proceso vivo."""
    return {"status": "ok"}


@router.get("/ready", tags=["health"])
async def readiness() -> dict[str, str]:
    """Readiness probe — DB alcanzable."""
    async with db_session() as db:
        await db.execute(text("SELECT 1"))
    return {"status": "ready"}
