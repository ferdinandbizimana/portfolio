"""Reading variance files and sending the follow-up e-mails (see app/variances.py)."""

import logging
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import datasets, variances
from app.core.config import Settings, get_settings
from app.core.mailer import Mailer
from app.db.models import DataFile, VarianceCase
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


def send_assignments(case_ids: list[int]) -> int:
    """Background job: e-mail the responsible people about newly assigned cases."""
    settings = get_settings()
    if not mail_ready(settings):
        logger.info("Variance e-mails not sent: SMTP is not set up")
        return 0
    with session_scope() as db:
        today = local_time(settings, datetime.now(UTC)).date()
        sent = _send(get_mailer(), variances.assignment_messages(db, settings, case_ids, today))
        for case in db.scalars(select(VarianceCase).where(VarianceCase.id.in_(case_ids))):
            if case.staff_id is not None:
                case.notified_at = datetime.now(UTC)
        db.commit()
    return sent


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
