"""Admin: the shared folder and the schedules that run analyses automatically."""

import re
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import func, select

from app.analyses.registry import get_analysis
from app.api.deps import CurrentUserDep, DbDep, NowDep, RedisDep, SettingsDep, client_ip
from app.api.uploads import QueueDep
from app.core import audit
from app.db.models import AnalysisRun, DataFile, Schedule
from app.jobs.scheduler import LAST_TICK_KEY, scan_now
from app.scheduling import DATE_RULES, fire, local_time, resolve_parameters

router = APIRouter(prefix="/api/admin", tags=["admin schedules"])

TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class InputRule(BaseModel):
    pattern: Annotated[str, Field(min_length=1, max_length=200)]
    sheet: Annotated[str, Field(max_length=100)] = ""


class ScheduleIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    analysis: Annotated[str, Field(max_length=64)]
    enabled: bool = True
    trigger: Literal["daily", "new_files"] = "daily"
    run_time: str = "06:00"
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    inputs: dict[str, InputRule] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    only_when_changed: bool = True
    notify: bool = True

    @field_validator("run_time")
    @classmethod
    def _time(cls, value: str) -> str:
        if not TIME.match(value):
            raise ValueError("Use a time like 06:00.")
        return value

    @field_validator("weekdays")
    @classmethod
    def _weekdays(cls, value: list[int]) -> list[int]:
        days = sorted(set(value))
        if not days or any(d < 0 or d > 6 for d in days):
            raise ValueError("Choose at least one day.")
        return days


class ScheduleOut(BaseModel):
    id: int
    name: str
    analysis: str
    analysis_title: str
    enabled: bool
    trigger: str
    run_time: str
    weekdays: list[int]
    inputs: dict[str, Any]
    parameters: dict[str, Any]
    only_when_changed: bool
    notify: bool
    last_fired_on: date | None
    last_message: str
    last_checked_at: str | None
    last_run_id: int | None
    last_run_status: str | None
    run_count: int


def _out(db: DbDep, schedule: Schedule) -> ScheduleOut:
    analysis = get_analysis(schedule.analysis_key)
    last_run = db.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.schedule_id == schedule.id)
        .order_by(AnalysisRun.id.desc())
        .limit(1)
    )
    count = db.scalar(
        select(func.count()).select_from(AnalysisRun).where(AnalysisRun.schedule_id == schedule.id)
    )
    return ScheduleOut(
        id=schedule.id,
        name=schedule.name,
        analysis=schedule.analysis_key,
        analysis_title=analysis.title if analysis else schedule.analysis_key,
        enabled=schedule.enabled,
        trigger=schedule.trigger,
        run_time=schedule.run_time,
        weekdays=schedule.weekdays,
        inputs=schedule.inputs,
        parameters=schedule.parameters,
        only_when_changed=schedule.only_when_changed,
        notify=schedule.notify,
        last_fired_on=schedule.last_fired_on,
        last_message=schedule.last_message,
        last_checked_at=schedule.last_checked_at.isoformat() if schedule.last_checked_at else None,
        last_run_id=last_run.id if last_run else None,
        last_run_status=last_run.status if last_run else None,
        run_count=count or 0,
    )


def _validate(body: ScheduleIn, today: date) -> None:
    analysis = get_analysis(body.analysis)
    if analysis is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown analysis.")
    errors = []
    keys = {spec.key for spec in analysis.inputs}
    for key in body.inputs:
        if key not in keys:
            errors.append(f"{analysis.title} has no input {key!r}.")
    for spec in analysis.inputs:
        if spec.required and spec.key not in body.inputs:
            errors.append(f"Give a file name pattern for {spec.label!r}.")
    for name, value in body.parameters.items():
        if isinstance(value, dict) and value.get("rule") not in DATE_RULES:
            errors.append(f"{name}: unknown date rule.")
    if not errors:
        try:
            analysis.Parameters.model_validate(resolve_parameters(body.parameters, today))
        except ValidationError as error:
            errors += [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors()]
    if errors:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, " ".join(errors))


def _apply(schedule: Schedule, body: ScheduleIn) -> None:
    changed_rules = (
        schedule.analysis_key != body.analysis
        or schedule.inputs != {k: v.model_dump() for k, v in body.inputs.items()}
        or schedule.parameters != body.parameters
    )
    schedule.name = body.name.strip()
    schedule.analysis_key = body.analysis
    schedule.enabled = body.enabled
    schedule.trigger = body.trigger
    schedule.run_time = body.run_time
    schedule.weekdays = body.weekdays
    schedule.inputs = {k: v.model_dump() for k, v in body.inputs.items()}
    schedule.parameters = body.parameters
    schedule.only_when_changed = body.only_when_changed
    schedule.notify = body.notify
    if changed_rules:
        schedule.last_signature = ""  # new rules: the next round may run again


def _schedule(db: DbDep, schedule_id: int) -> Schedule:
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Schedule not found.")
    return schedule


@router.get("/schedules/options")
def options(_: CurrentUserDep, settings: SettingsDep) -> dict[str, Any]:
    return {
        "date_rules": DATE_RULES,
        "timezone": settings.timezone,
        "folder_enabled": bool(settings.inbox_dir),
    }


@router.get("/schedules", response_model=list[ScheduleOut])
def list_schedules(_: CurrentUserDep, db: DbDep) -> list[ScheduleOut]:
    return [_out(db, s) for s in db.scalars(select(Schedule).order_by(Schedule.id)).all()]


@router.post("/schedules", response_model=ScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(
    body: ScheduleIn,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    now: NowDep,
) -> ScheduleOut:
    _validate(body, local_time(settings, now).date())
    schedule = Schedule(last_signature="", last_message="")
    _apply(schedule, body)
    db.add(schedule)
    db.flush()
    audit.record(
        db,
        "schedule.created",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=schedule.id,
        name=schedule.name,
    )
    db.commit()
    return _out(db, schedule)


@router.get("/schedules/{schedule_id}", response_model=ScheduleOut)
def read_schedule(schedule_id: int, _: CurrentUserDep, db: DbDep) -> ScheduleOut:
    return _out(db, _schedule(db, schedule_id))


@router.put("/schedules/{schedule_id}", response_model=ScheduleOut)
def update_schedule(
    schedule_id: int,
    body: ScheduleIn,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    now: NowDep,
) -> ScheduleOut:
    schedule = _schedule(db, schedule_id)
    _validate(body, local_time(settings, now).date())
    _apply(schedule, body)
    audit.record(
        db,
        "schedule.updated",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=schedule.id,
        enabled=schedule.enabled,
    )
    db.commit()
    return _out(db, schedule)


@router.delete("/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: int, request: Request, current: CurrentUserDep, db: DbDep) -> None:
    schedule = _schedule(db, schedule_id)
    audit.record(
        db,
        "schedule.deleted",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=schedule.id,
        name=schedule.name,
    )
    db.delete(schedule)
    db.commit()


@router.post("/schedules/{schedule_id}/run-now", response_model=ScheduleOut)
def run_now(
    schedule_id: int,
    current: CurrentUserDep,
    db: DbDep,
    queue: QueueDep,
    settings: SettingsDep,
    now: NowDep,
) -> ScheduleOut:
    """Start a run at once with the newest matching files, even if nothing changed."""
    schedule = _schedule(db, schedule_id)
    run = fire(
        db, queue, schedule, local_time(settings, now).date(), force=True, user_id=current.user.id
    )
    if run is None:
        raise HTTPException(status.HTTP_409_CONFLICT, schedule.last_message)
    return _out(db, schedule)


class FolderFile(BaseModel):
    id: int
    filename: str
    source_path: str | None
    status: str
    message: str
    created_at: str


class FolderStatus(BaseModel):
    enabled: bool
    settle_seconds: int
    interval_seconds: int
    timezone: str
    last_check: str | None
    files: list[FolderFile]


@router.get("/folder", response_model=FolderStatus)
def folder_status(
    _: CurrentUserDep, db: DbDep, settings: SettingsDep, redis: RedisDep
) -> FolderStatus:
    last = redis.get(LAST_TICK_KEY)
    files = db.scalars(
        select(DataFile).where(DataFile.source == "folder").order_by(DataFile.id.desc()).limit(20)
    ).all()
    return FolderStatus(
        enabled=bool(settings.inbox_dir),
        settle_seconds=settings.inbox_settle_seconds,
        interval_seconds=settings.scheduler_interval_seconds,
        timezone=settings.timezone,
        last_check=last.decode() if isinstance(last, bytes) else last,
        files=[
            FolderFile(
                id=f.id,
                filename=f.filename,
                source_path=f.source_path,
                status=f.status,
                message=f.message,
                created_at=f.created_at.isoformat(),
            )
            for f in files
        ],
    )


@router.post("/folder/scan", status_code=status.HTTP_202_ACCEPTED)
def scan_folder_now(
    request: Request, current: CurrentUserDep, db: DbDep, settings: SettingsDep, queue: QueueDep
) -> dict[str, str]:
    if not settings.inbox_dir:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The shared folder is not set up (INBOX_DIR)."
        )
    audit.record(
        db, "folder.scan_requested", user_id=current.user.id, ip_address=client_ip(request)
    )
    db.commit()
    queue.enqueue(scan_now, job_timeout=3600)
    return {"detail": "The folder is being checked."}
