"""Creating analysis runs: shared by the admin API and the scheduler."""

from collections.abc import Mapping
from typing import Any

from rq import Queue
from sqlalchemy.orm import Session

from app.analyses.base import Analysis, InputSpec
from app.datasets import ALL_SHEETS, recognised_sheets
from app.db.models import AnalysisRun, DataFile
from app.jobs.analysis import run_analysis

RUN_TIMEOUT_SECONDS = 3 * 3600


Choice = tuple[int, str]


def _check_file(
    db: Session, spec: InputSpec, data_file_id: int, sheet: str, errors: list[str]
) -> dict[str, Any] | None:
    data_file = db.get(DataFile, data_file_id)
    if data_file is None or data_file.status != "ready":
        errors.append(f"The file chosen for {spec.label!r} is not ready.")
        return None
    if spec.all_sheets:
        sheet = ALL_SHEETS
        if not recognised_sheets(data_file.sheets, spec.dataset):
            errors.append(f"{data_file.filename} has no sheet recognised for {spec.label!r}.")
            return None
    elif not any(s["name"] == sheet for s in data_file.sheets):
        errors.append(f"{data_file.filename} has no sheet {sheet!r}.")
        return None
    return {
        "data_file_id": data_file.id,
        "sheet": sheet,
        "filename": data_file.filename,
        "sha256": data_file.sha256,
    }


def resolve_inputs(
    db: Session, analysis: Analysis, choices: Mapping[str, Choice | list[Choice]]
) -> tuple[dict[str, Any], list[str]]:
    """Check the chosen (file id, sheet) per input; return the run inputs and any errors.

    An input that takes several files stores the first file as usual, the others
    under "more" and the byte-identical copies it left out under "skipped".
    """
    errors: list[str] = []
    inputs: dict[str, Any] = {}
    for spec in analysis.inputs:
        choice = choices.get(spec.key)
        chosen = [choice] if isinstance(choice, tuple) else list(choice or [])
        if not chosen:
            if spec.required:
                errors.append(f"Choose a file for {spec.label!r}.")
            continue
        if len(chosen) > 1 and not spec.multiple:
            errors.append(f"{spec.label!r} takes one file.")
            continue
        checked = [_check_file(db, spec, file_id, sheet, errors) for file_id, sheet in chosen]
        files = [f for f in checked if f is not None]
        if len(files) != len(checked):
            continue
        kept: list[dict[str, Any]] = []
        skipped: list[str] = []
        for item in files:
            if any(k["sha256"] == item["sha256"] for k in kept):
                skipped.append(item["filename"])
            else:
                kept.append(item)
        inputs[spec.key] = kept[0]
        if spec.multiple and (len(kept) > 1 or skipped):
            inputs[spec.key] = {**kept[0], "more": kept[1:], "skipped": skipped}
    return inputs, errors


def enqueue(db: Session, queue: Queue, run: AnalysisRun) -> None:
    """Hand a committed run to the worker."""
    job = queue.enqueue(run_analysis, run.id, job_timeout=RUN_TIMEOUT_SECONDS)
    db.refresh(run)
    if not run.job_id:
        run.job_id = job.id
        db.commit()
