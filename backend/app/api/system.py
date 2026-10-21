"""Admin: is everything running? Worker, scheduler, last backup, disk space."""

import json
import shutil
from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from rq import Worker

from app import __version__
from app.api.deps import CurrentUserDep, NowDep, RedisDep, SettingsDep
from app.api.uploads import StorageDep
from app.jobs.scheduler import LAST_TICK_KEY

router = APIRouter(prefix="/api/admin", tags=["admin system"])

State = Literal["ok", "warning", "error", "off"]

BACKUP_STATUS_KEY = "system/last-backup.json"
# A nightly backup older than this is late.
BACKUP_MAX_AGE_HOURS = 26
# Below this much free space for stored files, warn.
LOW_DISK_BYTES = 2 * 2**30


class Item(BaseModel):
    name: str
    state: State
    detail: str


class SystemStatus(BaseModel):
    version: str
    items: list[Item]


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _hours(seconds: float) -> str:
    hours = seconds / 3600
    return f"{hours:.0f} hours" if hours >= 2 else f"{seconds / 60:.0f} minutes"


def worker_item(redis: RedisDep) -> Item:
    count = Worker.count(connection=redis)
    if count:
        return Item(name="Worker", state="ok", detail=f"{count} running")
    return Item(name="Worker", state="error", detail="Not running: analyses and files will wait.")


def scheduler_item(redis: RedisDep, now: datetime, interval: int) -> Item:
    raw = redis.get(LAST_TICK_KEY)
    last = _parse_time(raw.decode() if isinstance(raw, bytes) else str(raw)) if raw else None
    if last is None:
        return Item(name="Scheduler", state="warning", detail="Has not checked in yet.")
    age = (now - last).total_seconds()
    if age > 3 * interval:
        return Item(
            name="Scheduler",
            state="error",
            detail=f"Last check {_hours(age)} ago: schedules and the shared folder wait.",
        )
    return Item(name="Scheduler", state="ok", detail=f"Last check {age:.0f} seconds ago")


def backup_item(storage: StorageDep, now: datetime) -> Item:
    path = storage.path(BACKUP_STATUS_KEY)
    if not path.is_file():
        return Item(name="Backups", state="off", detail="No backup has been made yet.")
    try:
        status = json.loads(path.read_text())
        finished = _parse_time(str(status["finished_at"]))
    except (ValueError, KeyError, TypeError):
        return Item(name="Backups", state="warning", detail="The backup status cannot be read.")
    if finished is None:
        return Item(name="Backups", state="warning", detail="The backup status cannot be read.")
    age = (now - finished).total_seconds()
    message = str(status.get("message", ""))
    if status.get("result") != "ok":
        return Item(name="Backups", state="error", detail=f"Last backup failed: {message}")
    if age > BACKUP_MAX_AGE_HOURS * 3600:
        return Item(name="Backups", state="error", detail=f"Last backup {_hours(age)} ago.")
    return Item(name="Backups", state="ok", detail=f"Last backup {_hours(age)} ago ({message})")


def disk_item(storage: StorageDep) -> Item:
    storage.root.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(storage.root)
    free_gb = usage.free / 2**30
    detail = f"{free_gb:.1f} GB free of {usage.total / 2**30:.1f} GB"
    return Item(
        name="Disk space", state="warning" if usage.free < LOW_DISK_BYTES else "ok", detail=detail
    )


@router.get("/system", response_model=SystemStatus)
def system_status(
    _: CurrentUserDep, redis: RedisDep, storage: StorageDep, settings: SettingsDep, now: NowDep
) -> SystemStatus:
    return SystemStatus(
        version=__version__,
        items=[
            worker_item(redis),
            scheduler_item(redis, now, settings.scheduler_interval_seconds),
            backup_item(storage, now),
            disk_item(storage),
        ],
    )
