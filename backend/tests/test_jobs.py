from fakeredis import FakeStrictRedis

from app.jobs.queue import get_queue
from app.jobs.tasks import ping


def test_ping_job_runs_and_reports_progress() -> None:
    queue = get_queue(connection=FakeStrictRedis(), name="test")
    queue._is_async = False  # run the job immediately in this process

    job = queue.enqueue(ping, "hello")

    assert job.is_finished
    assert job.return_value() == "hello"
    assert job.get_meta()["progress"] == 100
