"""Admin: available analyses, running them, results, reports and comparison."""

import shutil
from typing import Any

import pyarrow.parquet as pq
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import datasets
from app.analyses.dashboard import rows_of
from app.analyses.registry import all_analyses, get_analysis
from app.api.deps import CurrentUserDep, DbDep, client_ip
from app.api.uploads import QueueDep, StorageDep
from app.core import audit
from app.db.models import AnalysisRun
from app.runs import enqueue, resolve_inputs

router = APIRouter(prefix="/api/admin", tags=["admin analyses"])

REPORT_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "html": "text/html; charset=utf-8",
}
# An interactive dashboard opened in the browser runs in a sandbox: its own
# opaque origin, no access to this site's cookies or API, nothing loaded from
# outside (Chart.js and the data are inside the file).
DASHBOARD_POLICY = (
    "sandbox allow-scripts allow-downloads; default-src 'none'; "
    "script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; "
    "frame-ancestors 'none'"
)


class InputOut(BaseModel):
    key: str
    label: str
    dataset: str
    dataset_title: str
    required: bool
    all_sheets: bool = False


class AnalysisOut(BaseModel):
    key: str
    title: str
    version: str
    description: str
    demo: bool
    inputs: list[InputOut]
    parameters_schema: dict[str, Any]


class DatasetOut(BaseModel):
    key: str
    title: str
    description: str
    demo: bool
    columns: list[dict[str, Any]]


@router.get("/analyses", response_model=list[AnalysisOut])
def list_analyses(_: CurrentUserDep) -> list[AnalysisOut]:
    return [
        AnalysisOut(
            key=a.key,
            title=a.title,
            version=a.version,
            description=a.description,
            demo=a.demo,
            inputs=[
                InputOut(
                    key=i.key,
                    label=i.label,
                    dataset=i.dataset,
                    dataset_title=datasets.get(i.dataset).title,
                    required=i.required,
                    all_sheets=i.all_sheets,
                )
                for i in a.inputs
            ],
            parameters_schema=a.Parameters.model_json_schema(),
        )
        for a in all_analyses().values()
    ]


@router.get("/datasets", response_model=list[DatasetOut])
def list_datasets(_: CurrentUserDep) -> list[DatasetOut]:
    return [
        DatasetOut(
            key=d.key,
            title=d.title,
            description=d.description,
            demo=d.demo,
            columns=[
                {"name": c.name, "type": c.type, "required": c.required, "aliases": c.aliases}
                for c in d.columns
            ],
        )
        for d in datasets.all_datasets()
    ]


class InputChoice(BaseModel):
    data_file_id: int
    sheet: str


class RunCreate(BaseModel):
    analysis: str
    label: str = Field(default="", max_length=200)
    parameters: dict[str, Any] = Field(default_factory=dict)
    inputs: dict[str, InputChoice]


class RunSummary(BaseModel):
    id: int
    analysis_key: str
    analysis_title: str
    analysis_version: str
    label: str
    status: str
    progress: int
    message: str
    checks_passed: int
    checks_total: int
    created_at: str
    finished_at: str | None


class RunOut(RunSummary):
    parameters: dict[str, Any]
    inputs: dict[str, Any]
    errors: list[str]
    checks: list[dict[str, Any]]
    metrics: list[dict[str, Any]]
    dashboard: dict[str, Any] | None
    reports: list[dict[str, Any]]
    result_hash: str


def _summary_fields(run: AnalysisRun) -> dict[str, Any]:
    analysis = get_analysis(run.analysis_key)
    checks = run.checks or []
    return {
        "id": run.id,
        "analysis_key": run.analysis_key,
        "analysis_title": analysis.title if analysis else run.analysis_key,
        "analysis_version": run.analysis_version,
        "label": run.label,
        "status": run.status,
        "progress": run.progress,
        "message": run.message,
        "checks_passed": sum(1 for c in checks if c.get("passed")),
        "checks_total": len(checks),
        "created_at": run.created_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def _out(run: AnalysisRun) -> RunOut:
    return RunOut(
        **_summary_fields(run),
        parameters=run.parameters or {},
        inputs=run.inputs or {},
        errors=run.errors or [],
        checks=run.checks or [],
        metrics=run.metrics or [],
        dashboard=run.dashboard,
        reports=[{k: v for k, v in r.items() if k != "storage_key"} for r in (run.reports or [])],
        result_hash=run.result_hash,
    )


def _run(db: DbDep, run_id: int) -> AnalysisRun:
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.")
    return run


def _start(
    body: RunCreate,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    queue: QueueDep,
    rerun_of: int | None = None,
) -> RunOut:
    analysis = get_analysis(body.analysis)
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown analysis.")
    inputs, errors = resolve_inputs(
        db, analysis, {key: (c.data_file_id, c.sheet) for key, c in body.inputs.items()}
    )
    params = None
    try:
        params = analysis.Parameters.model_validate(body.parameters)
    except ValueError as error:
        errors.append(f"Parameters: {error}")
    if errors or params is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, " ".join(errors))
    run = AnalysisRun(
        analysis_key=analysis.key,
        analysis_version=analysis.version,
        label=body.label.strip(),
        parameters=params.model_dump(mode="json"),
        inputs=inputs,
        status="queued",
        message="Waiting for the worker",
    )
    db.add(run)
    db.flush()
    details: dict[str, Any] = {"id": run.id, "analysis": analysis.key, "label": run.label}
    if rerun_of is not None:
        details["rerun_of"] = rerun_of
    audit.record(
        db, "run.created", user_id=current.user.id, ip_address=client_ip(request), **details
    )
    db.commit()
    enqueue(db, queue, run)
    return _out(run)


@router.post("/runs", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def create_run(
    body: RunCreate, request: Request, current: CurrentUserDep, db: DbDep, queue: QueueDep
) -> RunOut:
    return _start(body, request, current, db, queue)


@router.post("/runs/{run_id}/rerun", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def rerun(
    run_id: int, request: Request, current: CurrentUserDep, db: DbDep, queue: QueueDep
) -> RunOut:
    """Run the analysis again on the same files, sheets and parameters, with the
    current version of the analysis (e.g. after a correction of its rules)."""
    old = _run(db, run_id)
    body = RunCreate(
        analysis=old.analysis_key,
        label=old.label,
        parameters=old.parameters or {},
        inputs={
            key: InputChoice(data_file_id=int(value["data_file_id"]), sheet=str(value["sheet"]))
            for key, value in (old.inputs or {}).items()
        },
    )
    return _start(body, request, current, db, queue, rerun_of=old.id)


@router.get("/runs", response_model=list[RunSummary])
def list_runs(
    _: CurrentUserDep, db: DbDep, analysis: str | None = Query(default=None, max_length=64)
) -> list[RunSummary]:
    query = select(AnalysisRun).order_by(AnalysisRun.id.desc())
    if analysis:
        query = query.where(AnalysisRun.analysis_key == analysis)
    return [RunSummary(**_summary_fields(r)) for r in db.scalars(query).all()]


@router.get("/runs/compare")
def compare_runs(
    _: CurrentUserDep, db: DbDep, a: int = Query(), b: int = Query()
) -> dict[str, Any]:
    """Side-by-side figures of two runs of the same analysis (e.g. March vs June)."""
    first, second = _run(db, a), _run(db, b)
    if first.analysis_key != second.analysis_key:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Only runs of the same analysis can be compared."
        )
    if first.status != "succeeded" or second.status != "succeeded":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Both runs must have finished.")
    second_values = {m["label"]: m for m in second.metrics or []}
    rows = []
    for metric in first.metrics or []:
        other = second_values.get(metric["label"])
        value_a = metric.get("value")
        value_b = other.get("value") if other else None
        difference: float | None = None
        change: float | None = None
        if isinstance(value_a, int | float) and isinstance(value_b, int | float):
            difference = value_b - value_a
            change = difference / abs(value_a) if value_a else None
        rows.append(
            {
                "label": metric["label"],
                "format": metric.get("format", "number"),
                "a": value_a,
                "b": value_b,
                "difference": difference,
                "change": change,
            }
        )
    return {
        "analysis_key": first.analysis_key,
        "a": RunSummary(**_summary_fields(first)).model_dump(),
        "b": RunSummary(**_summary_fields(second)).model_dump(),
        "metrics": rows,
    }


@router.get("/runs/{run_id}", response_model=RunOut)
def read_run(run_id: int, _: CurrentUserDep, db: DbDep) -> RunOut:
    return _out(_run(db, run_id))


@router.post("/runs/{run_id}/cancel", response_model=RunOut)
def cancel_run(run_id: int, request: Request, current: CurrentUserDep, db: DbDep) -> RunOut:
    run = _run(db, run_id)
    if run.status in ("queued", "running"):
        run.status = "cancelled"
        run.message = "Cancelled."
        audit.record(
            db, "run.cancelled", user_id=current.user.id, ip_address=client_ip(request), id=run_id
        )
        db.commit()
    return _out(run)


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_run(
    run_id: int, request: Request, current: CurrentUserDep, db: DbDep, storage: StorageDep
) -> None:
    run = _run(db, run_id)
    if run.status in ("queued", "running"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cancel the run before deleting it.")
    shutil.rmtree(storage.path(f"runs/{run_id}"), ignore_errors=True)
    db.delete(run)
    audit.record(
        db, "run.deleted", user_id=current.user.id, ip_address=client_ip(request), id=run_id
    )
    db.commit()


@router.get("/runs/{run_id}/reports/{report_key}")
def download_report(
    run_id: int, report_key: str, _: CurrentUserDep, db: DbDep, storage: StorageDep
) -> FileResponse:
    run = _run(db, run_id)
    report = next((r for r in run.reports or [] if r["key"] == report_key), None)
    if report is None or not storage.exists(report["storage_key"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found.")
    return FileResponse(
        storage.path(report["storage_key"]),
        media_type=REPORT_TYPES[report["kind"]],
        filename=report["filename"],
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/runs/{run_id}/reports/{report_key}/view")
def view_dashboard(
    run_id: int, report_key: str, _: CurrentUserDep, db: DbDep, storage: StorageDep
) -> FileResponse:
    """Open an interactive dashboard in the browser (sandboxed)."""
    run = _run(db, run_id)
    report = next((r for r in run.reports or [] if r["key"] == report_key), None)
    if report is None or report["kind"] != "html" or not storage.exists(report["storage_key"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dashboard not found.")
    return FileResponse(
        storage.path(report["storage_key"]),
        media_type=REPORT_TYPES["html"],
        content_disposition_type="inline",
        filename=report["filename"],
        headers={"Cache-Control": "private, no-store", "Content-Security-Policy": DASHBOARD_POLICY},
    )


@router.get("/runs/{run_id}/tables/{name}")
def read_table(
    run_id: int,
    name: str,
    _: CurrentUserDep,
    db: DbDep,
    storage: StorageDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    _run(db, run_id)
    if not name.replace("_", "").isalnum():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Table not found.")
    key = f"runs/{run_id}/tables/{name}.parquet"
    if not storage.exists(key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Table not found.")
    table = pq.read_table(storage.path(key))
    page = table.slice(offset, limit).to_pandas()
    return {
        "total": table.num_rows,
        "columns": [str(c) for c in table.column_names],
        "rows": rows_of(page),
    }
