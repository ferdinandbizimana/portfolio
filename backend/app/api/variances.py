"""Spot-check variance follow-up: admin pages and the secure link for staff.

Admin routes import the bin list and the variance files, show the cases and
let the admin reassign or close them. The public routes take a case's secret
token (from the e-mail) and show only that case: bin, product, quantities and
status, never other cases, files or people.
"""

from datetime import date, datetime
from typing import Annotated, Any, Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app import variances
from app.api.deps import CurrentUserDep, DbDep, NowDep, SettingsDep, client_ip
from app.api.files import StorageDep
from app.api.uploads import QueueDep
from app.core import audit
from app.db.models import BinOwner, DataFile, VarianceCase, VarianceStaff
from app.jobs.variances import FileProblem, read_dataset, send_pending_now
from app.reporting.documents import TableBlock
from app.reporting.excel import build_workbook
from app.scheduling import local_time

admin_router = APIRouter(prefix="/api/admin/variances", tags=["admin variances"])
public_router = APIRouter(prefix="/api/public/variances", tags=["public"])

Unit = Annotated[str, Field(max_length=40)]


class StaffOut(BaseModel):
    id: int
    name: str
    email: str
    active: bool
    bins: int


class CaseOut(BaseModel):
    id: int
    source: str
    source_title: str
    reference: str
    storage_bin: str
    product: str
    description: str
    batch: str
    system_qty: float | None
    counted_qty: float | None
    difference_qty: float
    found_on: date | None
    reported_by: str
    staff_id: int | None
    staff_name: str
    status: str
    colour: Literal["green", "amber", "red"]
    days_open: int
    reason: str
    root_cause: str
    corrected_qty: float | None
    responsible_unit: str
    action_taken: str
    corrected_by: str
    corrected_at: datetime | None
    created_at: datetime
    notified_at: datetime | None


class Overview(BaseModel):
    summary: list[dict[str, Any]]
    staff: list[StaffOut]
    cases: list[CaseOut]
    total: int
    units: list[str]
    root_causes: list[str]
    sources: dict[str, str]
    overdue_days: int
    bins: int
    pending: int  # new cases waiting for the day-close e-mail
    day_close_time: str
    progress: list[dict[str, Any]]


def _today(settings: Any, now: datetime) -> date:
    return local_time(settings, now).date()


def _case_out(case: VarianceCase, names: dict[int, str], today: date, settings: Any) -> CaseOut:
    return CaseOut(
        id=case.id,
        source=case.source,
        source_title=variances.SOURCES.get(case.source, case.source),
        reference=case.reference,
        storage_bin=case.storage_bin,
        product=case.product,
        description=case.description,
        batch=case.batch,
        system_qty=case.system_qty,
        counted_qty=case.counted_qty,
        difference_qty=case.difference_qty,
        found_on=case.found_on,
        reported_by=case.reported_by,
        staff_id=case.staff_id,
        staff_name=names.get(case.staff_id or -1, "Not assigned"),
        status=case.status,
        colour=variances.colour(case, today, settings),
        days_open=variances.days_open(case, today),
        reason=case.reason,
        root_cause=case.root_cause,
        corrected_qty=case.corrected_qty,
        responsible_unit=case.responsible_unit,
        action_taken=case.action_taken,
        corrected_by=case.corrected_by,
        corrected_at=case.corrected_at,
        created_at=case.created_at,
        notified_at=case.notified_at,
    )


def _filtered(
    db: Any, status_: str | None, staff_id: int | None, source: str | None
) -> list[VarianceCase]:
    query = select(VarianceCase).order_by(VarianceCase.created_at.desc(), VarianceCase.id.desc())
    if status_:
        query = query.where(VarianceCase.status == status_)
    if staff_id is not None:
        query = query.where(
            VarianceCase.staff_id.is_(None) if staff_id == 0 else VarianceCase.staff_id == staff_id
        )
    if source:
        query = query.where(VarianceCase.source == source)
    return list(db.scalars(query))


@admin_router.get("", response_model=Overview)
def overview(
    _: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    now: NowDep,
    state: Annotated[str | None, Query(alias="status", max_length=16)] = None,
    staff_id: int | None = None,
    source: Annotated[str | None, Query(max_length=24)] = None,
    colour: Annotated[str | None, Query(max_length=8)] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> Overview:
    today = _today(settings, now)
    staff = list(db.scalars(select(VarianceStaff).order_by(VarianceStaff.name)))
    names = {s.id: s.name for s in staff}
    counts = dict(
        db.execute(select(BinOwner.staff_id, func.count()).group_by(BinOwner.staff_id)).all()
    )
    cases = _filtered(db, state, staff_id, source)
    if colour:
        cases = [c for c in cases if variances.colour(c, today, settings) == colour]
    return Overview(
        summary=variances.summary(db, settings, today),
        staff=[
            StaffOut(id=s.id, name=s.name, email=s.email, active=s.active, bins=counts.get(s.id, 0))
            for s in staff
        ],
        cases=[_case_out(c, names, today, settings) for c in cases[:limit]],
        total=len(cases),
        units=variances.UNITS,
        root_causes=variances.ROOT_CAUSES,
        sources=variances.SOURCES,
        overdue_days=settings.variance_overdue_days,
        bins=sum(counts.values()),
        pending=len(variances.pending_cases(db)),
        day_close_time=settings.variance_day_close_time,
        progress=variances.progress(db),
    )


class FileChoice(BaseModel):
    data_file_id: int


def _file(db: Any, data_file_id: int) -> DataFile:
    data_file = db.get(DataFile, data_file_id)
    if data_file is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    return data_file  # type: ignore[no-any-return]


def _problem(error: FileProblem) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_CONTENT, {"message": str(error), "errors": error.details[:20]}
    )


@admin_router.post("/bin-list")
def import_bin_list(
    body: FileChoice,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    storage: StorageDep,
) -> dict[str, Any]:
    data_file = _file(db, body.data_file_id)
    try:
        _, frame, warnings = read_dataset(storage, data_file, ["bin_owners"])
    except FileProblem as error:
        raise _problem(error) from error
    result = variances.import_bin_list(db, frame, settings)
    audit.record(
        db,
        "variances.bin_list_imported",
        user_id=current.user.id,
        ip_address=client_ip(request),
        file=data_file.filename,
        staff=len(result.staff),
        bins=result.bins,
    )
    db.commit()
    return {
        "staff": result.staff,
        "bins": result.bins,
        "unit_bins": result.unit_bins,
        "emails": result.emails,
        "without_email": result.without_email,
        "warnings": [*warnings, *result.warnings],
    }


@admin_router.post("/import")
def import_variances(
    body: FileChoice,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    storage: StorageDep,
    queue: QueueDep,
) -> dict[str, Any]:
    data_file = _file(db, body.data_file_id)
    try:
        dataset, frame, warnings = read_dataset(storage, data_file, list(variances.DATASET_SOURCE))
    except FileProblem as error:
        raise _problem(error) from error
    source = variances.DATASET_SOURCE[dataset]
    result = variances.import_cases(
        db, source, frame, data_file.id, data_file.sha256, data_file.filename
    )
    audit.record(
        db,
        "variances.imported",
        user_id=current.user.id,
        ip_address=client_ip(request),
        file=data_file.filename,
        source=source,
        created=result.created,
    )
    db.commit()
    return {
        "source": source,
        "source_title": variances.SOURCES[source],
        "created": result.created,
        "duplicates": result.duplicates,
        "unassigned": result.unassigned,
        "no_variance": result.no_variance,
        "warnings": warnings[:20],
    }


@admin_router.post("/send-pending", status_code=status.HTTP_202_ACCEPTED)
def send_pending(
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    queue: QueueDep,
) -> dict[str, Any]:
    """E-mail the waiting new variances now, one e-mail per person."""
    if not (settings.smtp_host and settings.mail_from):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "E-mail is not set up: SMTP must be set on the server."
        )
    waiting = len(variances.pending_cases(db))
    queue.enqueue(send_pending_now, job_timeout=600)
    audit.record(
        db,
        "variances.mails_sent",
        user_id=current.user.id,
        ip_address=client_ip(request),
        cases=waiting,
    )
    db.commit()
    return {"status": "queued", "cases": waiting}


class StaffUpdate(BaseModel):
    email: Annotated[str, Field(max_length=320)] | None = None
    active: bool | None = None


@admin_router.patch("/staff/{staff_id}", response_model=StaffOut)
def update_staff(
    staff_id: int, body: StaffUpdate, request: Request, current: CurrentUserDep, db: DbDep
) -> StaffOut:
    person = db.get(VarianceStaff, staff_id)
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found.")
    if body.email is not None:
        email = body.email.strip().lower()
        if email and ("@" not in email or " " in email):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Not a valid e-mail address."
            )
        person.email = email
    if body.active is not None:
        person.active = body.active
    audit.record(
        db,
        "variances.staff_updated",
        user_id=current.user.id,
        ip_address=client_ip(request),
        staff=person.name,
    )
    db.commit()
    bins = db.scalar(
        select(func.count()).select_from(BinOwner).where(BinOwner.staff_id == person.id)
    )
    return StaffOut(
        id=person.id, name=person.name, email=person.email, active=person.active, bins=bins or 0
    )


class CaseUpdate(BaseModel):
    staff_id: int | None


@admin_router.patch("/cases/{case_id}", response_model=CaseOut)
def reassign(
    case_id: int,
    body: CaseUpdate,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    now: NowDep,
    queue: QueueDep,
) -> CaseOut:
    case = db.get(VarianceCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variance not found.")
    if body.staff_id is not None and db.get(VarianceStaff, body.staff_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Staff member not found.")
    case.staff_id = body.staff_id
    audit.record(
        db,
        "variances.reassigned",
        user_id=current.user.id,
        ip_address=client_ip(request),
        case=case.id,
        staff_id=body.staff_id,
    )
    if case.status == variances.OPEN:
        case.notified_at = None  # the new person gets it with the next e-mail
    db.commit()
    names = {s.id: s.name for s in db.scalars(select(VarianceStaff))}
    return _case_out(case, names, _today(settings, now), settings)


class Correction(BaseModel):
    root_cause: Annotated[str, Field(max_length=120)]
    corrected_qty: float | None = None
    reason: Annotated[str, Field(min_length=3, max_length=2000)]
    responsible_unit: Unit
    action_taken: Annotated[str, Field(max_length=2000)] = ""
    corrected_by: Annotated[str, Field(max_length=200)] = ""


@admin_router.post("/cases/{case_id}/correct", response_model=CaseOut)
def admin_correct(
    case_id: int,
    body: Correction,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    now: NowDep,
) -> CaseOut:
    case = db.get(VarianceCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variance not found.")
    _apply(case, body, now)
    audit.record(
        db,
        "variances.corrected",
        user_id=current.user.id,
        ip_address=client_ip(request),
        case=case.id,
        unit=case.responsible_unit,
    )
    db.commit()
    names = {s.id: s.name for s in db.scalars(select(VarianceStaff))}
    return _case_out(case, names, _today(settings, now), settings)


@admin_router.post("/cases/{case_id}/reopen", response_model=CaseOut)
def reopen(
    case_id: int,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    now: NowDep,
) -> CaseOut:
    case = db.get(VarianceCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variance not found.")
    case.status, case.corrected_at = variances.OPEN, None
    audit.record(
        db,
        "variances.reopened",
        user_id=current.user.id,
        ip_address=client_ip(request),
        case=case.id,
    )
    db.commit()
    names = {s.id: s.name for s in db.scalars(select(VarianceStaff))}
    return _case_out(case, names, _today(settings, now), settings)


@admin_router.get("/cases/{case_id}/link")
def case_link(case_id: int, _: CurrentUserDep, db: DbDep, settings: SettingsDep) -> dict[str, str]:
    case = db.get(VarianceCase, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Variance not found.")
    return {"link": variances.link(settings, case)}


@admin_router.get("/export.xlsx")
def export(_: CurrentUserDep, db: DbDep, settings: SettingsDep, now: NowDep) -> Response:
    today = _today(settings, now)
    names = {s.id: s.name for s in db.scalars(select(VarianceStaff))}
    rows = [_case_out(c, names, today, settings) for c in _filtered(db, None, None, None)]
    columns = {
        "id": "Case",
        "source_title": "Source",
        "reference": "Reference",
        "storage_bin": "Storage Bin",
        "product": "Product",
        "description": "Description",
        "batch": "Batch",
        "system_qty": "System Qty",
        "counted_qty": "Counted Qty",
        "difference_qty": "Difference",
        "found_on": "Found On",
        "reported_by": "Reported By",
        "staff_name": "Responsible",
        "status": "Status",
        "colour": "Colour",
        "days_open": "Days Open",
        "root_cause": "Root Cause",
        "corrected_qty": "Quantity Corrected",
        "reason": "Reason",
        "responsible_unit": "Responsible Unit",
        "action_taken": "Action Taken",
        "corrected_by": "Corrected By",
        "corrected_at": "Corrected At",
    }
    cases = pd.DataFrame(
        [{label: getattr(r, key) for key, label in columns.items()} for r in rows],
        columns=list(columns.values()),
    )
    cases["Corrected At"] = cases["Corrected At"].map(
        lambda v: v.strftime("%Y-%m-%d %H:%M") if v is not None and not pd.isna(v) else ""
    )
    by_person = pd.DataFrame(variances.summary(db, settings, today)).rename(
        columns={
            "name": "Responsible",
            "open": "Open",
            "overdue": "Overdue",
            "corrected": "Corrected",
        }
    )
    by_person = by_person.drop(columns="staff_id") if "staff_id" in by_person else by_person
    progress = pd.DataFrame(
        variances.progress(db),
        columns=[
            "file",
            "source",
            "imported_at",
            "lines",
            "variances",
            "corrected",
            "open",
            "line_accuracy_before",
            "line_accuracy_now",
            "quantity_accuracy_before",
            "quantity_accuracy_now",
        ],
    ).rename(
        columns={
            "file": "File",
            "source": "Source",
            "imported_at": "Imported",
            "lines": "Lines Checked",
            "variances": "Variances",
            "corrected": "Corrected",
            "open": "Open",
            "line_accuracy_before": "Line Accuracy Before",
            "line_accuracy_now": "Line Accuracy Now",
            "quantity_accuracy_before": "Quantity Accuracy Before",
            "quantity_accuracy_now": "Quantity Accuracy Now",
        }
    )
    progress["Imported"] = progress["Imported"].map(
        lambda v: v.strftime("%Y-%m-%d") if v is not None and not pd.isna(v) else ""
    )
    content = build_workbook(
        "Stock variance follow-up",
        f"Situation on {today:%d %B %Y}",
        [],
        [
            TableBlock(
                "Accuracy progress",
                progress,
                {
                    "Lines Checked": "integer",
                    "Variances": "integer",
                    "Corrected": "integer",
                    "Open": "integer",
                    "Line Accuracy Before": "percent",
                    "Line Accuracy Now": "percent",
                    "Quantity Accuracy Before": "percent",
                    "Quantity Accuracy Now": "percent",
                },
            ),
            TableBlock(
                "By person",
                by_person,
                {"Open": "integer", "Overdue": "integer", "Corrected": "integer"},
            ),
            TableBlock(
                "Variances",
                cases,
                {
                    "Difference": "number",
                    "System Qty": "number",
                    "Counted Qty": "number",
                    "Quantity Corrected": "number",
                    "Days Open": "integer",
                },
            ),
        ],
        [],
    )
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="Variance_Follow_Up_{today:%Y-%m-%d}.xlsx"'
            )
        },
    )


# --- The secure link ------------------------------------------------------------------------


class PublicCase(BaseModel):
    """What the person with the link sees: this case only."""

    storage_bin: str
    product: str
    description: str
    batch: str
    source_title: str
    system_qty: float | None
    counted_qty: float | None
    difference_qty: float
    found_on: date | None
    responsible: str
    status: str
    colour: str
    days_open: int
    overdue_days: int
    reason: str
    root_cause: str
    corrected_qty: float | None
    responsible_unit: str
    action_taken: str
    corrected_by: str
    corrected_at: datetime | None
    units: list[str]
    root_causes: list[str]


def _by_token(db: Any, token: str) -> VarianceCase:
    case = db.scalar(select(VarianceCase).where(VarianceCase.token == token))
    if case is None or len(token) < 20:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link is not valid.")
    return case  # type: ignore[no-any-return]


def _public(db: Any, case: VarianceCase, settings: Any, now: datetime) -> PublicCase:
    today = _today(settings, now)
    person = db.get(VarianceStaff, case.staff_id) if case.staff_id else None
    return PublicCase(
        storage_bin=case.storage_bin,
        product=case.product,
        description=case.description,
        batch=case.batch,
        source_title=variances.SOURCES.get(case.source, case.source),
        system_qty=case.system_qty,
        counted_qty=case.counted_qty,
        difference_qty=case.difference_qty,
        found_on=case.found_on,
        responsible=person.name if person else "",
        status=case.status,
        colour=variances.colour(case, today, settings),
        days_open=variances.days_open(case, today),
        overdue_days=settings.variance_overdue_days,
        reason=case.reason,
        root_cause=case.root_cause,
        corrected_qty=case.corrected_qty,
        responsible_unit=case.responsible_unit,
        action_taken=case.action_taken,
        corrected_by=case.corrected_by,
        corrected_at=case.corrected_at,
        units=variances.UNITS,
        root_causes=variances.ROOT_CAUSES,
    )


def _apply(case: VarianceCase, body: Correction, now: datetime) -> None:
    try:
        variances.correct(
            case,
            body.reason,
            body.responsible_unit,
            body.action_taken,
            body.corrected_by,
            now,
            root_cause=body.root_cause,
            corrected_qty=body.corrected_qty,
        )
    except variances.CaseClosed as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error


@public_router.get("/{token}", response_model=PublicCase)
def public_case(token: str, db: DbDep, settings: SettingsDep, now: NowDep) -> PublicCase:
    return _public(db, _by_token(db, token), settings, now)


@public_router.post("/{token}/correct", response_model=PublicCase)
def public_correct(
    token: str, body: Correction, request: Request, db: DbDep, settings: SettingsDep, now: NowDep
) -> PublicCase:
    case = _by_token(db, token)
    _apply(case, body, now)
    audit.record(
        db,
        "variances.corrected",
        ip_address=client_ip(request),
        case=case.id,
        unit=case.responsible_unit,
        by=case.corrected_by,
        via="link",
    )
    db.commit()
    return _public(db, case, settings, now)
