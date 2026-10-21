"""Entry point of the worker container: `python -m app.jobs.worker`."""

from rq import Worker

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.jobs.queue import DEFAULT_QUEUE, get_redis


def main() -> None:
    configure_logging(get_settings().log_level)
    worker = Worker([DEFAULT_QUEUE], connection=get_redis())
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
