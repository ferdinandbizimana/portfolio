"""Shared folder pickup, schedules and notifications."""

import os
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from fakeredis import FakeStrictRedis
from fastapi.testclient import TestClient
from rq import Queue
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import AnalysisRun, AuditEvent, DataFile, Schedule
from app.jobs import notify, scheduler
from app.scheduling import is_due, resolve_date_rule, tick
from app.storage import LocalStorage
from tests.conftest import FakeMailer
from tests.samples import demo_csv, demo_workbook

pytestmark = pytest.mark.usefixtures("jobs")

# 2026-07-02 08:00 in Kigali (UTC+2), a Thursday.
NOW = datetime(2026, 7, 2, 6, 0, tzinfo=UTC)
OLD = NOW.timestamp() - 3600  # modification time of a settled file


@pytest.fixture
def inbox(tmp_path: Path) -> Path:
    path = tmp_path / "inbox"
    path.mkdir()
    return path


@pytest.fixture
def folder_settings(settings: Settings, inbox: Path) -> Settings:
    settings.inbox_dir = str(inbox)
    settings.inbox_settle_seconds = 60
    return settings


@pytest.fixture
def queue(redis: FakeStrictRedis) -> Queue:
    return Queue("test", connection=redis, is_async=False)


@pytest.fixture
def sent(
    monkeypatch: pytest.MonkeyPatch, mailer: FakeMailer, folder_settings: Settings
) -> Iterator[FakeMailer]:
    monkeypatch.setattr(notify, "get_mailer", lambda: mailer)
    monkeypatch.setattr(notify, "get_settings", lambda: folder_settings)
    yield mailer


def drop(inbox: Path, name: str, content: bytes, mtime: float = OLD) -> Path:
    path = inbox / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, (mtime, mtime))
    return path


def make_schedule(db: Session, **fields: Any) -> Schedule:
    values: dict[str, Any] = {
        "name": "Daily stock",
        "analysis_key": "demo_stock_summary",
        "trigger": "daily",
        "run_time": "07:00",
        "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "inputs": {"stock": {"pattern": "stock*.xlsx", "sheet": ""}},
        "parameters": {"period_end": {"rule": "previous_month_end"}},
        "only_when_changed": True,
        "notify": True,
        "last_signature": "",
        "last_message": "",
    }
    values.update(fields)
    schedule = Schedule(**values)
    db.add(schedule)
    db.commit()
    return schedule


def runs(db: Session) -> list[AnalysisRun]:
    db.expire_all()
    return list(db.scalars(select(AnalysisRun).order_by(AnalysisRun.id)).all())


# --- date rules and timing -------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "today", "expected"),
    [
        ("run_date", date(2026, 7, 2), date(2026, 7, 2)),
        ("previous_day", date(2026, 7, 1), date(2026, 6, 30)),
        ("previous_month_end", date(2026, 7, 2), date(2026, 6, 30)),
        ("previous_month_end", date(2026, 1, 15), date(2025, 12, 31)),
        ("previous_month_end", date(2028, 3, 1), date(2028, 2, 29)),
    ],
)
def test_date_rules(rule: str, today: date, expected: date) -> None:
    assert resolve_date_rule(rule, today) == expected


def test_daily_schedule_is_due_once_per_day_after_its_time() -> None:
    schedule = Schedule(enabled=True, trigger="daily", run_time="07:00", weekdays=[3])
    thursday_early = datetime(2026, 7, 2, 6, 59)
    thursday_late = datetime(2026, 7, 2, 7, 0)
    assert not is_due(schedule, thursday_early)
    assert is_due(schedule, thursday_late)
    schedule.last_fired_on = date(2026, 7, 2)
    assert not is_due(schedule, thursday_late)
    friday = datetime(2026, 7, 3, 9, 0)
    assert not is_due(schedule, friday)  # not one of its days
    schedule.weekdays, schedule.enabled = [4], False
    assert not is_due(schedule, friday)


# --- shared folder ---------------------------------------------------------


def test_folder_picks_up_settled_files_only(
    db: Session, storage: LocalStorage, queue: Queue, folder_settings: Settings, inbox: Path
) -> None:
    drop(inbox, "stock june.xlsx", demo_workbook())
    drop(inbox, "plant 2/stock.csv", demo_csv())
    drop(inbox, "copying.xlsx", demo_workbook(), mtime=NOW.timestamp() - 5)
    drop(inbox, "~$stock june.xlsx", b"lock")
    drop(inbox, ".hidden.csv", demo_csv())
    drop(inbox, "readme.pdf", b"%PDF")
    drop(inbox, "notes.txt", b"\x00\x01binary")

    tick(db, storage, queue, folder_settings, NOW)

    db.expire_all()
    files = {f.source_path: f for f in db.scalars(select(DataFile)).all()}
    assert set(files) == {"notes.txt", "plant 2/stock.csv", "stock june.xlsx"}
    assert files["stock june.xlsx"].status == "ready"
    assert files["stock june.xlsx"].source == "folder"
    assert files["plant 2/stock.csv"].filename == "stock.csv"
    assert files["notes.txt"].status == "failed"
    assert "not an Excel or CSV file" in files["notes.txt"].message
    # The shared folder itself is never changed.
    assert (inbox / "stock june.xlsx").exists()
    events = db.scalars(select(AuditEvent).where(AuditEvent.action == "data.picked_up")).all()
    assert len(events) == 3

    # Once the copy has finished, the file is picked up too.
    later = datetime.fromtimestamp(NOW.timestamp() + 120, UTC)
    tick(db, storage, queue, folder_settings, later)
    db.expire_all()
    assert db.scalar(select(DataFile).where(DataFile.source_path == "copying.xlsx")) is not None


def test_folder_takes_a_file_again_only_when_its_content_changes(
    db: Session, storage: LocalStorage, queue: Queue, folder_settings: Settings, inbox: Path
) -> None:
    path = drop(inbox, "stock.xlsx", demo_workbook())
    tick(db, storage, queue, folder_settings, NOW)
    tick(db, storage, queue, folder_settings, NOW)
    assert len(db.scalars(select(DataFile)).all()) == 1

    # Saved again with the same content: not a new file.
    os.utime(path, (OLD + 10, OLD + 10))
    tick(db, storage, queue, folder_settings, NOW)
    assert len(db.scalars(select(DataFile)).all()) == 1

    drop(inbox, "stock.xlsx", demo_workbook(rows=[["P100", "M-1", "Gloves", 1, 2]]), OLD + 20)
    tick(db, storage, queue, folder_settings, NOW)
    db.expire_all()
    files = db.scalars(select(DataFile).order_by(DataFile.id)).all()
    assert len(files) == 2
    assert files[0].sha256 != files[1].sha256
    assert files[1].status == "ready"


def test_folder_pickup_is_off_without_inbox_dir(
    db: Session, storage: LocalStorage, queue: Queue, settings: Settings
) -> None:
    assert settings.inbox_dir == ""
    tick(db, storage, queue, settings, NOW)
    assert db.scalars(select(DataFile)).all() == []


# --- schedules -------------------------------------------------------------


def test_daily_schedule_runs_on_the_newest_matching_file(
    db: Session,
    storage: LocalStorage,
    queue: Queue,
    folder_settings: Settings,
    inbox: Path,
    sent: FakeMailer,
) -> None:
    drop(inbox, "stock may.xlsx", demo_workbook(rows=[["P1", "M-1", "A", 1, 100]]))
    tick(db, storage, queue, folder_settings, NOW)
    drop(inbox, "stock june.xlsx", demo_workbook(), OLD + 1)
    drop(inbox, "other.xlsx", demo_workbook(), OLD + 2)
    schedule = make_schedule(db)

    started = tick(db, storage, queue, folder_settings, NOW)

    assert len(started) == 1
    [run] = runs(db)
    assert run.status == "succeeded", run.message
    assert run.schedule_id == schedule.id
    assert run.inputs["stock"]["filename"] == "stock june.xlsx"
    assert run.inputs["stock"]["sheet"] == "Stock"
    assert run.parameters == {"period_end": "2026-06-30"}
    assert run.label == "Daily stock (2026-07-02)"
    db.refresh(schedule)
    assert schedule.last_fired_on == date(2026, 7, 2)
    assert "run #" in schedule.last_message

    # The owner is told, with a link to the run.
    [message] = sent.sent
    assert message["To"] == "owner@example.com"
    assert message["Subject"] == "[Portfolio] Daily stock: run finished"
    body = message.get_content()
    assert "Self-checks: 3 of 3 passed" in body
    assert f"/admin/runs/{run.id}" in body

    # Same day again: nothing new.
    assert tick(db, storage, queue, folder_settings, NOW) == []

    # Next day, same files: no new run, and the reason is shown.
    next_day = datetime(2026, 7, 3, 6, 0, tzinfo=UTC)
    assert tick(db, storage, queue, folder_settings, next_day) == []
    db.refresh(schedule)
    assert "no new files" in schedule.last_message
    assert len(runs(db)) == 1

    # A new export arrives: the following day runs again.
    drop(inbox, "stock july.xlsx", demo_workbook(rows=[["P1", "M-1", "A", 5, 500]]), OLD + 3)
    third_day = datetime(2026, 7, 4, 6, 0, tzinfo=UTC)
    assert len(tick(db, storage, queue, folder_settings, third_day)) == 1
    assert runs(db)[-1].inputs["stock"]["filename"] == "stock july.xlsx"


def test_new_files_schedule_waits_for_its_files(
    db: Session,
    storage: LocalStorage,
    queue: Queue,
    folder_settings: Settings,
    inbox: Path,
    sent: FakeMailer,
) -> None:
    schedule = make_schedule(
        db,
        trigger="new_files",
        inputs={"stock": {"pattern": "*.csv", "sheet": "CSV"}},
        parameters={"period_end": "2026-06-30"},
        notify=False,
    )
    assert tick(db, storage, queue, folder_settings, NOW) == []
    db.refresh(schedule)
    assert schedule.last_message.startswith("Waiting: No ready file named like '*.csv'")

    drop(inbox, "exports/stock.csv", demo_csv())
    # The file is picked up and read in this round, and the run starts at once.
    assert len(tick(db, storage, queue, folder_settings, NOW)) == 1
    assert tick(db, storage, queue, folder_settings, NOW) == []
    [run] = runs(db)
    assert run.status == "succeeded"
    assert sent.sent == []  # notifications switched off for this schedule


def test_mail_problem_does_not_change_the_run(
    db: Session,
    storage: LocalStorage,
    queue: Queue,
    folder_settings: Settings,
    inbox: Path,
    sent: FakeMailer,
) -> None:
    sent.fail = True
    drop(inbox, "stock.xlsx", demo_workbook())
    make_schedule(db)
    tick(db, storage, queue, folder_settings, NOW)
    [run] = runs(db)
    assert run.status == "succeeded"


# --- admin API -------------------------------------------------------------


SCHEDULE_BODY: dict[str, Any] = {
    "name": "Morning stock",
    "analysis": "demo_stock_summary",
    "trigger": "daily",
    "run_time": "06:30",
    "weekdays": [0, 1, 2, 3, 4],
    "inputs": {"stock": {"pattern": "stock*.xlsx"}},
    "parameters": {"period_end": {"rule": "previous_month_end"}},
}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"analysis": "nope"}, "Unknown analysis."),
        ({"inputs": {}}, "Give a file name pattern for"),
        ({"parameters": {"period_end": {"rule": "someday"}}}, "unknown date rule"),
        ({"parameters": {}}, "period_end: Field required"),
        ({"run_time": "25:00"}, "Use a time like 06:00."),
        ({"weekdays": []}, "Choose at least one day."),
    ],
)
def test_schedule_is_checked_when_saved(
    logged_in: TestClient, change: dict[str, Any], message: str
) -> None:
    response = logged_in.post("/api/admin/schedules", json={**SCHEDULE_BODY, **change})
    assert response.status_code in (400, 422)
    assert message in response.text


def test_schedule_crud_run_now_and_audit(
    logged_in: TestClient,
    db: Session,
    storage: LocalStorage,
    queue: Queue,
    folder_settings: Settings,
    inbox: Path,
) -> None:
    # Switched off, so that only "Run now" starts runs here.
    created = logged_in.post("/api/admin/schedules", json={**SCHEDULE_BODY, "enabled": False})
    assert created.status_code == 201, created.text
    schedule = created.json()
    assert schedule["analysis_title"] == "Demo: stock value by plant"
    assert schedule["weekdays"] == [0, 1, 2, 3, 4]

    # No file yet: run now explains what is missing.
    missing = logged_in.post(f"/api/admin/schedules/{schedule['id']}/run-now")
    assert missing.status_code == 409
    assert "No ready file named like 'stock*.xlsx'" in missing.json()["detail"]

    drop(inbox, "stock.xlsx", demo_workbook())
    tick(db, storage, queue, folder_settings, NOW)
    ran = logged_in.post(f"/api/admin/schedules/{schedule['id']}/run-now")
    assert ran.status_code == 200, ran.text
    assert ran.json()["run_count"] == 1
    # Run now always runs, even if nothing changed.
    again = logged_in.post(f"/api/admin/schedules/{schedule['id']}/run-now")
    assert again.json()["run_count"] == 2
    assert again.json()["last_run_status"] == "succeeded"

    updated = logged_in.put(
        f"/api/admin/schedules/{schedule['id']}", json={**SCHEDULE_BODY, "run_time": "05:00"}
    )
    assert updated.json()["enabled"] is True
    assert updated.json()["run_time"] == "05:00"
    assert [s["name"] for s in logged_in.get("/api/admin/schedules").json()] == ["Morning stock"]

    assert logged_in.delete(f"/api/admin/schedules/{schedule['id']}").status_code == 204
    assert logged_in.get(f"/api/admin/schedules/{schedule['id']}").status_code == 404
    # The runs stay.
    assert len(runs(db)) == 2
    assert all(run.schedule_id is None for run in runs(db))

    actions = [e.action for e in db.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()]
    for action in ("schedule.created", "schedule.fired", "schedule.updated", "schedule.deleted"):
        assert action in actions


def test_folder_status_and_scan_button(
    logged_in: TestClient,
    client: TestClient,
    settings: Settings,
    inbox: Path,
    redis: FakeStrictRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    off = logged_in.post("/api/admin/folder/scan")
    assert off.status_code == 409
    assert logged_in.get("/api/admin/folder").json()["enabled"] is False

    settings.inbox_dir = str(inbox)
    monkeypatch.setattr(scheduler, "get_settings", lambda: settings)
    monkeypatch.setattr(scheduler, "get_redis", lambda: redis)
    monkeypatch.setattr(
        scheduler, "get_queue", lambda _: Queue("t", connection=redis, is_async=False)
    )
    drop(inbox, "stock.xlsx", demo_workbook())
    assert logged_in.post("/api/admin/folder/scan").status_code == 202

    status = logged_in.get("/api/admin/folder").json()
    assert status["enabled"] is True
    assert status["timezone"] == "Africa/Kigali"
    [picked] = status["files"]
    assert picked["source_path"] == "stock.xlsx"
    assert picked["status"] == "ready"
    data_files = logged_in.get("/api/admin/data-files").json()
    assert data_files[0]["source"] == "folder"

    options = logged_in.get("/api/admin/schedules/options").json()
    assert options["date_rules"]["previous_month_end"] == "Last day of the previous month"


def test_schedules_need_login(client: TestClient) -> None:
    assert client.get("/api/admin/schedules").status_code == 401
    assert client.post("/api/admin/schedules", json=SCHEDULE_BODY).status_code in (401, 403)
    assert client.get("/api/admin/folder").status_code == 401


def test_scheduler_lock_lets_only_one_scheduler_act(
    redis: FakeStrictRedis, monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    calls: list[datetime] = []

    def fake_tick(*args: Any) -> list[AnalysisRun]:
        calls.append(args[-1])
        return []

    monkeypatch.setattr(scheduler, "get_settings", lambda: settings)
    monkeypatch.setattr(scheduler, "tick", fake_tick)
    assert scheduler.run_once(redis) is True
    assert scheduler.run_once(redis) is False
    assert len(calls) == 1
    assert redis.get(scheduler.LAST_TICK_KEY) is not None
