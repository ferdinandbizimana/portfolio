"""Entry point of the scheduler container: `python -m app.jobs.scheduler`.

Every `SCHEDULER_INTERVAL_SECONDS` it picks up new files from the shared
folder and starts the scheduled runs that are due. The runs themselves are
done by the worker. A Redis lock makes sure that only one scheduler acts,
even if two are started by mistake.
"""

import logging
import time
from datetime import UTC, datetime

from redis import Redis

from app import storage as storage_module
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import session_scope
from app.jobs.queue import get_queue, get_redis
from app.scheduling import scan_shared_folder, tick

logger = logging.getLogger(__name__)

LOCK_KEY = "scheduler:lock"
LAST_TICK_KEY = "scheduler:last_tick"


def run_once(redis: Redis) -> bool:
    """One round, if no other scheduler holds the lock. Returns whether it ran."""
    settings = get_settings()
    if not redis.set(LOCK_KEY, "1", nx=True, ex=max(settings.scheduler_interval_seconds - 1, 1)):
        return False
    now = datetime.now(UTC)
    with session_scope() as db:
        started = tick(db, storage_module.get_storage(), get_queue(redis), settings, now)
    redis.set(LAST_TICK_KEY, now.isoformat())
    for run in started:
        logger.info("Scheduled run %s started", run.id)
    return True


def scan_now() -> None:
    """Background job for the "Check the folder now" button."""
    settings = get_settings()
    redis = get_redis()
    with session_scope() as db:
        scan_shared_folder(
            db, storage_module.get_storage(), get_queue(redis), settings, datetime.now(UTC)
        )


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    redis = get_redis()
    logger.info(
        "Scheduler started: every %ss, shared folder %s, time zone %s",
        settings.scheduler_interval_seconds,
        settings.inbox_dir or "(off)",
        settings.timezone,
    )
    while True:
        try:
            run_once(redis)
        except Exception:
            logger.exception("Scheduler round failed")
        time.sleep(settings.scheduler_interval_seconds)


if __name__ == "__main__":
    main()
