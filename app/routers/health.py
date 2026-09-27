"""Health check routes (liveness always up; readiness depends on MongoDB)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Response, status

from app.db import get_database_state, is_database_ready

router = APIRouter(tags=["health"])


def _liveness_payload() -> dict:
    return {
        "status": "OK",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "notes-service",
    }


@router.get("/health")
@router.get("/health/live")
async def liveness() -> dict:
    """Liveness probe — process is up; does not depend on MongoDB."""
    return _liveness_payload()


@router.get("/health/ready")
async def readiness(response: Response) -> dict:
    """Readiness probe — 200 only when MongoDB is connected."""
    database = get_database_state()
    if is_database_ready():
        return {
            "status": "OK",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "notes-service",
            "database": database,
        }

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "unavailable",
        "reason": "database",
        "database": database,
        "service": "notes-service",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
