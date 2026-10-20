"""Smoke test for a running stack: enqueue a job and wait for the worker.

Run inside the backend container: `python -m app.jobs.smoke`. Exits non-zero
if the worker does not finish the job within the timeout.
"""

import sys
import time

from app.jobs.queue import get_queue
from app.jobs.tasks import ping


def main(timeout_seconds: float = 30.0) -> int:
    job = get_queue().enqueue(ping, "smoke")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if job.is_finished:
            print("worker ok")
            return 0
        if job.is_failed:
            break
        time.sleep(0.5)
    print(f"worker did not finish the job (status: {job.get_status()})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
