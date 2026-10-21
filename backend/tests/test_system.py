"""Admin system status: worker, scheduler, backups, disk."""

import json
from datetime import timedelta

from fakeredis import FakeStrictRedis
from fastapi.testclient import TestClient

from app.jobs.scheduler import LAST_TICK_KEY
from app.storage import LocalStorage
from tests.conftest import Clock


def items(client: TestClient) -> dict[str, dict[str, str]]:
    response = client.get("/api/admin/system")
    assert response.status_code == 200, response.text
    return {item["name"]: item for item in response.json()["items"]}


def write_backup_status(storage: LocalStorage, **status: str) -> None:
    path = storage.path("system/last-backup.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status))


def test_nothing_running_yet(logged_in: TestClient) -> None:
    status = items(logged_in)
    assert status["Worker"]["state"] == "error"
    assert status["Scheduler"]["state"] == "warning"
    assert status["Backups"] == {
        "name": "Backups",
        "state": "off",
        "detail": "No backup has been made yet.",
    }
    assert status["Disk space"]["state"] in ("ok", "warning")
    assert "GB free" in status["Disk space"]["detail"]


def test_scheduler_and_backup_ages(
    logged_in: TestClient, redis: FakeStrictRedis, clock: Clock, storage: LocalStorage
) -> None:
    redis.set(LAST_TICK_KEY, (clock.now - timedelta(seconds=30)).isoformat())
    write_backup_status(
        storage,
        result="ok",
        finished_at=(clock.now - timedelta(hours=5)).isoformat().replace("+00:00", "Z"),
        message="Snapshot 1a2b3c4d",
    )
    status = items(logged_in)
    assert status["Scheduler"] == {
        "name": "Scheduler",
        "state": "ok",
        "detail": "Last check 30 seconds ago",
    }
    assert status["Backups"]["state"] == "ok"
    assert status["Backups"]["detail"] == "Last backup 5 hours ago (Snapshot 1a2b3c4d)"

    # A day later nothing has happened (times moved back; the login stays valid).
    redis.set(LAST_TICK_KEY, (clock.now - timedelta(hours=24)).isoformat())
    write_backup_status(
        storage,
        result="ok",
        finished_at=(clock.now - timedelta(hours=29)).isoformat(),
        message="Snapshot 1a2b3c4d",
    )
    status = items(logged_in)
    assert status["Scheduler"]["state"] == "error"
    assert status["Backups"]["state"] == "error"
    assert status["Backups"]["detail"] == "Last backup 29 hours ago."


def test_failed_backup_is_shown(logged_in: TestClient, clock: Clock, storage: LocalStorage) -> None:
    write_backup_status(
        storage, result="failed", finished_at=clock.now.isoformat(), message="Repository locked"
    )
    assert items(logged_in)["Backups"] == {
        "name": "Backups",
        "state": "error",
        "detail": "Last backup failed: Repository locked",
    }


def test_system_status_needs_login(client: TestClient) -> None:
    assert client.get("/api/admin/system").status_code == 401
