"""Entry point of the scheduler container: `python -m app.jobs.scheduler`.

Every `SCHEDULER_INTERVAL_SECONDS` it picks up new files from the shared
folder, starts the scheduled runs that are due, on working days from
`VARIANCE_REMINDER_TIME` sends each person their list of open stock variances,
and on the last day of each month sends the expiry follow-up. The runs
themselves are done by the worker. A Redis lock makes sure that only one
scheduler acts, even if two are started by mistake.
"""

import logging
import time
from datetime import UTC, datetime

from redis import Redis

from app import storage as storage_module
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import session_scope
from app.jobs.expiry import send_monthly
from app.jobs.notify import get_mailer
from app.jobs.queue import get_queue, get_redis
from app.jobs.variances import send_digests
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
        try:
            if send_monthly(db, settings, now, get_mailer(), storage_module.get_storage()):
                logger.info("Sent the monthly expiry follow-up")
        except Exception:
            logger.exception("Could not send the monthly expiry follow-up")
            db.rollback()
        try:
            sent = send_digests(db, settings, now, get_mailer())
            if sent:
                logger.info("Sent %s lists of open stock variances", sent)
        except Exception:
            logger.exception("Could not send the lists of open stock variances")
            db.rollback()
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
