"""Creating analysis runs: shared by the admin API and the scheduler."""

from typing import Any

from rq import Queue
from sqlalchemy.orm import Session

from app.analyses.base import Analysis
from app.db.models import AnalysisRun, DataFile
from app.jobs.analysis import run_analysis

RUN_TIMEOUT_SECONDS = 3 * 3600


def resolve_inputs(
    db: Session, analysis: Analysis, choices: dict[str, tuple[int, str]]
) -> tuple[dict[str, Any], list[str]]:
    """Check the chosen (file id, sheet) per input; return the run inputs and any errors."""
    errors: list[str] = []
    inputs: dict[str, Any] = {}
    for spec in analysis.inputs:
        choice = choices.get(spec.key)
        if choice is None:
            if spec.required:
                errors.append(f"Choose a file for {spec.label!r}.")
            continue
        data_file_id, sheet = choice
        data_file = db.get(DataFile, data_file_id)
        if data_file is None or data_file.status != "ready":
            errors.append(f"The file chosen for {spec.label!r} is not ready.")
            continue
        if not any(s["name"] == sheet for s in data_file.sheets):
            errors.append(f"{data_file.filename} has no sheet {sheet!r}.")
            continue
        inputs[spec.key] = {
            "data_file_id": data_file.id,
            "sheet": sheet,
            "filename": data_file.filename,
            "sha256": data_file.sha256,
        }
    return inputs, errors


def enqueue(db: Session, queue: Queue, run: AnalysisRun) -> None:
    """Hand a committed run to the worker."""
    job = queue.enqueue(run_analysis, run.id, job_timeout=RUN_TIMEOUT_SECONDS)
    db.refresh(run)
    if not run.job_id:
        run.job_id = job.id
        db.commit()
