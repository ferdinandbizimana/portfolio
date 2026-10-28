"""Reading variance files and sending the follow-up e-mails (see app/variances.py)."""

import logging
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
from sqlalchemy.orm import Session

from app import datasets, variances
from app.core.config import Settings, get_settings
from app.core.mailer import Mailer
from app.db.models import DataFile
from app.db.session import session_scope
from app.jobs.ingest import parsed_dir_key
from app.jobs.notify import get_mailer
from app.scheduling import local_time
from app.storage import LocalStorage

logger = logging.getLogger(__name__)


class FileProblem(Exception):
    def __init__(self, message: str, details: list[str] | None = None) -> None:
        super().__init__(message)
        self.details = details or []


def read_dataset(
    storage: LocalStorage, data_file: DataFile, dataset_keys: list[str]
) -> tuple[str, pd.DataFrame, list[str]]:
    """The first sheet of the file recognised as one of the datasets.

    Values that cannot be read in optional columns (a date typed by hand, for
    example) are left empty and reported as warnings; a problem in a required
    column refuses the file.
    """
    if data_file.status != "ready":
        raise FileProblem(f"{data_file.filename} is not ready yet.")
    for sheet in data_file.sheets:
        found = [m.get("dataset") for m in sheet.get("matches", [])]
        key = next((k for k in dataset_keys if k in found), None)
        if key is None:
            continue
        spec = datasets.get(key)
        path = storage.path(f"{parsed_dir_key(data_file)}/{sheet['parquet_path']}")
        wanted = datasets.source_columns(spec, list(sheet["columns"]))
        raw = pq.read_table(path, columns=wanted or None).to_pandas()
        coerced = datasets.coerce(spec, raw, header_row=int(sheet["header_row"]))
        required = {c.name for c in spec.columns if c.required}
        texts = [i.text(data_file.filename, sheet["name"]) for i in coerced.issues]
        if any(i.column in required for i in coerced.issues) or (coerced.frame.empty and texts):
            raise FileProblem(f"{data_file.filename} does not match {spec.title!r}.", texts)
        return key, coerced.frame, [f"{t} (left empty)" for t in texts]
    titles = ", ".join(repr(datasets.get(k).title) for k in dataset_keys)
    raise FileProblem(f"{data_file.filename} has no sheet recognised as {titles}.")


def _send(mailer: Mailer, messages: list[Any]) -> int:
    sent = 0
    for message in messages:
        try:
            mailer.send(message)
            sent += 1
        except Exception:
            logger.exception("Could not send a variance e-mail to %s", message["To"])
    return sent


def mail_ready(settings: Settings) -> bool:
    return bool(settings.smtp_host and settings.mail_from)


def send_pending(
    db: Session, settings: Settings, now: datetime, mailer: Mailer, force: bool = False
) -> int:
    """The day's new variances, one e-mail per person: when the day closes, or at once.

    Cases created after today's close time wait for the next day's close.
    """
    if not mail_ready(settings):
        return 0
    local_now = local_time(settings, now)
    if not force and not variances.day_closed(settings, local_now):
        return 0
    cases = variances.pending_cases(db)
    if not force:
        hours, minutes = (int(p) for p in settings.variance_day_close_time.split(":"))
        close = local_now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        cases = [
            c for c in cases if c.created_at is None or local_time(settings, c.created_at) < close
        ]
    today = local_now.date()
    sent = 0
    for items, message in variances.assignment_messages(db, settings, cases, today):
        try:
            mailer.send(message)
        except Exception:
            logger.exception("Could not send the new variances to %s", message["To"])
            continue
        sent += 1
        for case in items:
            case.notified_at = now
    db.commit()
    return sent


def send_pending_now() -> int:
    """Background job: the admin's "Send e-mails now"."""
    settings = get_settings()
    with session_scope() as db:
        return send_pending(db, settings, datetime.now(UTC), get_mailer(), force=True)


def send_digests(db: Session, settings: Settings, now: datetime, mailer: Mailer) -> int:
    """The morning list of open variances, once a working day per person."""
    local_now = local_time(settings, now)
    if not mail_ready(settings) or not variances.digest_due(settings, local_now):
        return 0
    today = local_now.date()
    sent = 0
    for person, message in variances.digest_messages(db, settings, today):
        try:
            mailer.send(message)
            sent += 1
        except Exception:
            logger.exception("Could not send the variance list to %s", person.email)
            continue
        person.last_digest_on = today
    db.commit()
    return sent
