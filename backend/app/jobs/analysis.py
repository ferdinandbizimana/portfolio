"""Background job: run an analysis on its input files.

Steps: load and validate each input → compute → check the language of the
dashboard → store tables and a result hash → build reports (language checked)
→ done. Progress and messages are written to the run so the admin page can
follow along. A run marked "cancelled" stops at the next step.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import datasets
from app import storage as storage_module
from app.analyses.base import AnalysisResult
from app.analyses.dashboard import MAX_DASHBOARD_ROWS, Dashboard
from app.analyses.registry import get_analysis
from app.db.models import AnalysisRun, DataFile, ReportTemplate
from app.db.session import session_scope
from app.jobs.ingest import parsed_dir_key
from app.reporting.documents import Templates
from app.reporting.guard import BannedWordingError, check_report, find_banned
from app.reporting.word import TemplateError
from app.storage import LocalStorage

logger = logging.getLogger(__name__)


class RunStopped(Exception):
    pass


class RunFailed(Exception):
    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


def _now() -> datetime:
    return datetime.now(UTC)


def _step(db: Session, run: AnalysisRun, progress: int, message: str) -> None:
    db.refresh(run, ["status"])
    if run.status == "cancelled":
        raise RunStopped
    run.progress = progress
    run.message = message
    db.commit()


def load_input(
    db: Session, storage: LocalStorage, spec: datasets.DatasetSpec, choice: dict[str, Any]
) -> pd.DataFrame:
    data_file = db.get(DataFile, choice.get("data_file_id"))
    if data_file is None or data_file.status != "ready":
        raise RunFailed(f"The file chosen for {spec.title!r} is not available.")
    sheet = next((s for s in data_file.sheets if s["name"] == choice.get("sheet")), None)
    if sheet is None:
        raise RunFailed(f"{data_file.filename}: sheet {choice.get('sheet')!r} was not found.")
    path = storage.path(f"{parsed_dir_key(data_file)}/{sheet['parquet_path']}")
    # Read only the columns this dataset uses: SAP exports often have many more.
    wanted = datasets.source_columns(spec, list(sheet["columns"]))
    raw = pq.read_table(path, columns=wanted or None).to_pandas()
    coerced = datasets.coerce(spec, raw, header_row=int(sheet["header_row"]))
    if not coerced.ok:
        raise RunFailed(
            f"{data_file.filename} does not match {spec.title!r}.",
            [issue.text(data_file.filename, sheet["name"]) for issue in coerced.issues],
        )
    return coerced.frame


HASH_CHUNK_ROWS = 100_000


def result_hash(result: AnalysisResult) -> str:
    """SHA-256 of the result data, to prove that the same inputs give the same result."""
    digest = hashlib.sha256()
    for name in sorted(result.tables):
        digest.update(name.encode())
        frame = result.tables[name]
        digest.update(",".join(map(str, frame.columns)).encode())
        for start in range(0, len(frame), HASH_CHUNK_ROWS):  # in pieces: tables can be huge
            chunk = frame.iloc[start : start + HASH_CHUNK_ROWS]
            digest.update(chunk.to_csv(index=False, header=False, lineterminator="\n").encode())
    digest.update(
        json.dumps(
            {
                "metrics": [k.model_dump() for k in result.metrics],
                "checks": [c.out().model_dump() for c in result.checks],
            },
            sort_keys=True,
            default=str,
        ).encode()
    )
    return digest.hexdigest()


def _templates(db: Session, storage: LocalStorage) -> Templates:
    active = db.scalars(select(ReportTemplate).where(ReportTemplate.active.is_(True))).all()
    paths = {t.kind: storage.path(t.storage_key) for t in active}
    return Templates(docx=paths.get("docx"), pptx=paths.get("pptx"))


def run_analysis(run_id: int) -> None:
    storage = storage_module.get_storage()
    with session_scope() as db:
        run = db.get(AnalysisRun, run_id)
        if run is None or run.status != "queued":
            return
        run.status = "running"
        run.started_at = _now()
        db.commit()
        try:
            _execute(db, storage, run)
        except RunStopped:
            run.message = "Cancelled."
        except RunFailed as failure:
            run.status = "failed"
            run.message = str(failure)
            run.errors = failure.errors
        except Exception:
            logger.exception("Run %s failed", run_id)
            db.rollback()
            run.status = "failed"
            run.message = "The analysis stopped because of an unexpected error. See the server log."
        else:
            run.status = "succeeded"
            run.progress = 100
        run.finished_at = _now()
        db.commit()


def _execute(db: Session, storage: LocalStorage, run: AnalysisRun) -> None:
    analysis = get_analysis(run.analysis_key)
    if analysis is None:
        raise RunFailed(f"Unknown analysis {run.analysis_key!r}.")
    try:
        params = analysis.Parameters.model_validate(run.parameters)
    except ValidationError as error:
        messages = [str(e["msg"]) for e in error.errors()]
        raise RunFailed("The parameters are not valid.", messages) from None

    _step(db, run, 5, "Checking the input files")
    data: dict[str, pd.DataFrame] = {}
    errors: list[str] = []
    for spec in analysis.inputs:
        choice = run.inputs.get(spec.key)
        if not choice:
            if spec.required:
                errors.append(f"No file was chosen for {spec.label!r}.")
            continue
        try:
            data[spec.key] = load_input(db, storage, datasets.get(spec.dataset), choice)
        except RunFailed as failure:
            errors += failure.errors or [str(failure)]
    if errors:
        raise RunFailed("Some input files are not right. Nothing was calculated.", errors)

    _step(db, run, 40, "Calculating")
    result = analysis.compute(data, params)

    _step(db, run, 60, "Checking the wording")
    found = find_banned(_dashboard_texts(result))
    if found:
        raise RunFailed("The dashboard contains banned wording.", found)

    _step(db, run, 65, "Saving the results")
    base = f"runs/{run.id}"
    tables_dir = storage.path(f"{base}/tables")
    tables_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in result.tables.items():
        frame.to_parquet(tables_dir / f"{name}.parquet", index=False)
    run.result_hash = result_hash(result)
    run.checks = [c.out().model_dump() for c in result.checks]
    run.metrics = [k.model_dump() for k in result.metrics]
    run.dashboard = cap_dashboard(result.dashboard).model_dump()

    _step(db, run, 75, "Writing the reports")
    reports_dir = storage.path(f"{base}/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    stored: list[dict[str, Any]] = []
    try:
        reports = analysis.reports(result, params, _templates(db, storage))
    except TemplateError as error:
        raise RunFailed(f"The active report template cannot be used: {error}") from None
    for report in reports:
        try:
            check_report(report.kind, report.content)
        except BannedWordingError as error:
            raise RunFailed(f"{report.filename} contains banned wording.", [str(error)]) from None
        key = f"{base}/reports/{report.filename}"
        storage.path(key).write_bytes(report.content)
        stored.append(
            {
                "key": report.key,
                "title": report.title,
                "kind": report.kind,
                "filename": report.filename,
                "storage_key": key,
                "size_bytes": len(report.content),
            }
        )
    run.reports = stored
    failed = sum(not c.passed for c in result.checks)
    run.message = (
        "All checks passed." if not failed else f"{failed} check(s) failed. Review before use."
    )


def cap_dashboard(dashboard: Dashboard) -> Dashboard:
    """Keep dashboards light: very long tables show their first rows only.

    The full tables stay in the run's stored tables and in the Excel workbook.
    """
    tables = []
    for table in dashboard.tables:
        total = max(table.total_rows or 0, len(table.rows))
        if total > MAX_DASHBOARD_ROWS or len(table.rows) < total:
            shown = min(len(table.rows), MAX_DASHBOARD_ROWS)
            note = (
                f"Showing the first {shown:,} of {total:,} lines. "
                "All lines are in the Excel workbook."
            )
            table = table.model_copy(
                update={
                    "rows": table.rows[:MAX_DASHBOARD_ROWS],
                    "total_rows": total,
                    "note": f"{table.note} {note}".strip(),
                }
            )
        tables.append(table)
    return dashboard.model_copy(update={"tables": tables})


def _dashboard_texts(result: AnalysisResult) -> list[str]:
    dashboard = result.dashboard
    texts = [dashboard.title, dashboard.subtitle, *dashboard.notes]
    texts += [k.label for k in dashboard.kpis] + [c.title for c in dashboard.charts]
    texts += [c.label for c in dashboard.checks]
    for table in dashboard.tables:
        texts += [table.title, table.note, *(c.label for c in table.columns)]
    return texts
