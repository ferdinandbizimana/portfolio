"""Job functions run by the worker.

`ping` is a trivial job used to prove that the worker picks up work.
Analysis and report jobs are added in Phase 4.
"""

from rq import get_current_job


def ping(message: str = "pong") -> str:
    job = get_current_job()
    if job is not None:
        job.meta["progress"] = 100
        job.save_meta()  # type: ignore[no-untyped-call]
    return message
