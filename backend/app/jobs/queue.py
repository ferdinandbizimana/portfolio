"""Background job queue (Redis + RQ)."""

from redis import Redis
from rq import Queue

from app.core.config import get_settings

DEFAULT_QUEUE = "default"


def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def get_queue(connection: Redis | None = None, name: str = DEFAULT_QUEUE) -> Queue:
    return Queue(name, connection=connection or get_redis())
