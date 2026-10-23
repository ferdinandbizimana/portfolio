"""Schedules: run an analysis automatically on the newest matching files.

A schedule names, for each input of its analysis, a file name pattern such as
``MB5B*.xlsx``. When it fires, the newest ready file matching each pattern is
used. A date parameter may be a rule (for example "last day of the previous
month"); the rule is turned into a fixed date when the run is created and the
fixed date is what the run stores, so the run itself stays reproducible.
"""

import hashlib
import json
import logging
from datetime import date, datetime, timedelta
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from rq import Queue
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analyses.base import Analysis
from app.analyses.registry import get_analysis
from app.core import audit
from app.core.config import Settings
from app.datasets import ALL_SHEETS, recognised_sheets
from app.datasources.folder import ScanResult, scan_folder
from app.db.models import AnalysisRun, DataFile, Schedule
from app.runs import enqueue, resolve_inputs
from app.storage import LocalStorage

logger = logging.getLogger(__name__)

DATE_RULES = {
    "run_date": "Date of the run",
    "previous_day": "Day before the run",
    "previous_month_end": "Last day of the previous month",
}

# How many of the newest ready files are searched for a match.
SEARCH_LIMIT = 500


def resolve_date_rule(rule: str, today: date) -> date:
    if rule == "run_date":
        return today
    if rule == "previous_day":
        return today - timedelta(days=1)
    if rule == "previous_month_end":
        return today.replace(day=1) - timedelta(days=1)
    raise ValueError(f"Unknown date rule {rule!r}.")


def resolve_parameters(parameters: dict[str, Any], today: date) -> dict[str, Any]:
    """Replace {"rule": ...} values by the date they stand for."""
    resolved: dict[str, Any] = {}
    for name, value in parameters.items():
        if isinstance(value, dict) and "rule" in value:
            resolved[name] = resolve_date_rule(str(value["rule"]), today).isoformat()
        else:
            resolved[name] = value
    return resolved


def _matches(pattern: str, data_file: DataFile) -> bool:
    pattern = pattern.strip().lower()
    names = [data_file.filename.lower()]
    if data_file.source_path:
        names.append(data_file.source_path.lower())
    return any(fnmatchcase(name, pattern) for name in names)


def pick_files(
    db: Session, analysis: Analysis, schedule: Schedule
) -> tuple[dict[str, tuple[int, str]], list[str]]:
    """The newest ready file (and sheet) for each input, or why there is none."""
    recent = db.scalars(
        select(DataFile)
        .where(DataFile.status == "ready")
        .order_by(DataFile.id.desc())
        .limit(SEARCH_LIMIT)
        # The worker may have read new files since this session loaded them.
        .execution_options(populate_existing=True)
    ).all()
    choices: dict[str, tuple[int, str]] = {}
    errors: list[str] = []
    for spec in analysis.inputs:
        config = schedule.inputs.get(spec.key) or {}
        pattern = str(config.get("pattern", "")).strip()
        wanted_sheet = str(config.get("sheet", "")).strip()
        if not pattern:
            if spec.required:
                errors.append(f"No file name pattern is set for {spec.label!r}.")
            continue
        found = None
        for data_file in recent:
            if not _matches(pattern, data_file):
                continue
            if spec.all_sheets:
                if recognised_sheets(data_file.sheets, spec.dataset):
                    found = (data_file.id, ALL_SHEETS)
                    break
                continue
            for sheet in data_file.sheets:
                if wanted_sheet:
                    ok = sheet["name"] == wanted_sheet
                else:
                    ok = any(m["dataset"] == spec.dataset for m in sheet.get("matches", []))
                if ok:
                    found = (data_file.id, str(sheet["name"]))
                    break
            if found:
                break
        if found:
            choices[spec.key] = found
        elif spec.required:
            where = f"sheet {wanted_sheet!r}" if wanted_sheet else "a recognised sheet"
            errors.append(f"No ready file named like {pattern!r} with {where} for {spec.label!r}.")
    return choices, errors


def signature(inputs: dict[str, Any], parameters: dict[str, Any]) -> str:
    """Identifies the input files and parameters, to notice when nothing changed."""
    content = {
        "inputs": {k: [v["sha256"], v["sheet"]] for k, v in sorted(inputs.items())},
        "parameters": parameters,
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()


def is_due(schedule: Schedule, local_now: datetime) -> bool:
    if not schedule.enabled:
        return False
    if schedule.trigger == "new_files":
        return True
    hour, minute = (int(part) for part in schedule.run_time.split(":"))
    return (
        local_now.weekday() in schedule.weekdays
        and (local_now.hour, local_now.minute) >= (hour, minute)
        and schedule.last_fired_on != local_now.date()
    )


def fire(
    db: Session,
    queue: Queue,
    schedule: Schedule,
    today: date,
    *,
    force: bool = False,
    user_id: int | None = None,
) -> AnalysisRun | None:
    """Start a run for the schedule, unless files are missing or nothing changed."""
    analysis = get_analysis(schedule.analysis_key)
    if analysis is None:
        schedule.last_message = f"The analysis {schedule.analysis_key!r} no longer exists."
        db.commit()
        return None
    choices, errors = pick_files(db, analysis, schedule)
    inputs, input_errors = resolve_inputs(db, analysis, choices)
    errors += input_errors
    try:
        parameters = resolve_parameters(schedule.parameters, today)
        params = analysis.Parameters.model_validate(parameters).model_dump(mode="json")
    except (ValueError, ValidationError) as error:
        errors.append(f"Parameters: {error}")
        params = {}
    if errors:
        schedule.last_message = "Waiting: " + " ".join(errors)
        db.commit()
        return None
    sig = signature(inputs, params)
    check_changed = schedule.only_when_changed or schedule.trigger == "new_files"
    if not force and check_changed and sig == schedule.last_signature:
        if schedule.trigger == "daily":
            schedule.last_fired_on = today
            schedule.last_message = (
                f"{today.isoformat()}: no new files since the last run, so no new run."
            )
        db.commit()
        return None
    run = AnalysisRun(
        analysis_key=analysis.key,
        analysis_version=analysis.version,
        label=f"{schedule.name} ({today.isoformat()})"[:200],
        parameters=params,
        inputs=inputs,
        status="queued",
        message="Waiting for the worker",
        schedule_id=schedule.id,
    )
    db.add(run)
    db.flush()
    schedule.last_signature = sig
    schedule.last_fired_on = today
    schedule.last_message = f"{today.isoformat()}: run #{run.id} started."
    audit.record(
        db,
        "schedule.fired",
        user_id=user_id,
        id=schedule.id,
        run_id=run.id,
        analysis=analysis.key,
        manual=force,
    )
    db.commit()
    enqueue(db, queue, run)
    return run


def local_time(settings: Settings, now: datetime) -> datetime:
    return now.astimezone(ZoneInfo(settings.timezone))


def scan_shared_folder(
    db: Session, storage: LocalStorage, queue: Queue, settings: Settings, now: datetime
) -> ScanResult | None:
    if not settings.inbox_dir:
        return None
    return scan_folder(
        db,
        storage,
        queue,
        Path(settings.inbox_dir),
        now=now.timestamp(),
        settle_seconds=settings.inbox_settle_seconds,
        max_bytes=settings.data_upload_max_mb * 2**20,
    )


def tick(
    db: Session, storage: LocalStorage, queue: Queue, settings: Settings, now: datetime
) -> list[AnalysisRun]:
    """One scheduler round: pick up new files, then start the runs that are due."""
    scan_shared_folder(db, storage, queue, settings, now)
    local_now = local_time(settings, now)
    started = []
    schedules = db.scalars(select(Schedule).where(Schedule.enabled.is_(True))).all()
    for schedule in schedules:
        schedule.last_checked_at = now
        if not is_due(schedule, local_now):
            continue
        try:
            run = fire(db, queue, schedule, local_now.date())
        except Exception:
            logger.exception("Schedule %s could not start a run", schedule.id)
            db.rollback()
            continue
        if run is not None:
            started.append(run)
    db.commit()
    return started
