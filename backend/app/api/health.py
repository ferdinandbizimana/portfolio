"""Health check: is the API up, and can it reach the database and Redis?"""

from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine

DependencyCheck = Callable[[], None]


def check_database() -> None:
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))


def check_redis() -> None:
    client = Redis.from_url(get_settings().redis_url, socket_connect_timeout=2)
    try:
        client.ping()
    finally:
        client.close()


def get_checks() -> dict[str, DependencyCheck]:
    return {"database": check_database, "redis": check_redis}


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, Literal["ok", "error"]]


router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
def health(
    response: Response,
    checks: Annotated[dict[str, DependencyCheck], Depends(get_checks)],
) -> HealthResponse:
    results: dict[str, Literal["ok", "error"]] = {}
    for name, check in checks.items():
        try:
            check()
        except Exception:
            results[name] = "error"
        else:
            results[name] = "ok"
    healthy = all(result == "ok" for result in results.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="ok" if healthy else "degraded", checks=results)
