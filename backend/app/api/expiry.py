"""Monthly expiry follow-up: admin pages and the secure link for the sales pharmacist.

Admin routes list the expiry monitoring runs, prepare a run's follow-up, send
the e-mail and download the justifications. The public routes take a review's
secret token (from the e-mail) and show only that month's outlook per plant and
the expired items to justify.
"""

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import expiry
from app.api.deps import CurrentUserDep, DbDep, NowDep, SettingsDep, client_ip
from app.api.files import StorageDep
from app.api.uploads import QueueDep
from app.core import audit
from app.db.models import AnalysisRun, ExpiryJustification, ExpiryReview
from app.jobs.expiry import ready, send_now

admin_router = APIRouter(prefix="/api/admin/expiry", tags=["admin expiry"])
public_router = APIRouter(prefix="/api/public/expiry", tags=["public"])


class ItemOut(BaseModel):
    id: int
    kind: str  # expired | projected
    band: str  # projected: Within 3 months | 3 to 6 months
    material: str
    description: str
    owner: str
    plants: str
    value: float
    root_cause: str
    reason: str
    justified_by: str
    justified_at: datetime | None


class PlantOutlook(BaseModel):
    plant: str
    plant_name: str
    expired: float
    within_3_months: float
    three_to_6_months: float


class ReviewOut(BaseModel):
    id: int
    run_id: int
    closing_date: date
    mailed_month: str
    mailed_at: datetime | None
    items: int
    justified: int
    expired_value: float
    projected: int
    measured: int
    link: str


class RunRow(BaseModel):
    run_id: int
    label: str
    opening_date: str
    closing_date: str
    created_at: datetime
    review: ReviewOut | None


class Overview(BaseModel):
    runs: list[RunRow]
    mail_ready: bool
    root_causes: list[str]
    measures: list[str]


class ReviewDetail(BaseModel):
    review: ReviewOut
    items: list[ItemOut]
    outlook: list[PlantOutlook]
    root_causes: list[str]
    measures: list[str]


class Justification(BaseModel):
    root_cause: str = Field(max_length=120)
    reason: str = Field(default="", max_length=4000)
    justified_by: str = Field(default="", max_length=200)


def _items(db: Any, review: ExpiryReview) -> list[ExpiryJustification]:
    return list(
        db.scalars(
            select(ExpiryJustification)
            .where(ExpiryJustification.review_id == review.id)
            .order_by(ExpiryJustification.value.desc(), ExpiryJustification.material)
        )
    )


def _review_out(db: Any, settings: Any, review: ExpiryReview) -> ReviewOut:
    everything = _items(db, review)
    items = [i for i in everything if i.kind != expiry.PROJECTED]
    projected = [i for i in everything if i.kind == expiry.PROJECTED]
    return ReviewOut(
        id=review.id,
        run_id=review.run_id,
        closing_date=review.closing_date,
        mailed_month=review.mailed_month,
        mailed_at=review.mailed_at,
        items=len(items),
        justified=sum(1 for i in items if i.root_cause),
        expired_value=sum(i.value for i in items),
        projected=len(projected),
        measured=sum(1 for i in projected if i.root_cause),
        link=expiry.link(settings, review),
    )


def _item_out(item: ExpiryJustification) -> ItemOut:
    return ItemOut(
        id=item.id,
        kind=item.kind,
        band=item.band,
        material=item.material,
        description=item.description,
        owner=item.owner,
        plants=item.plants,
        value=item.value,
        root_cause=item.root_cause,
        reason=item.reason,
        justified_by=item.justified_by,
        justified_at=item.justified_at,
    )


def _detail(db: Any, settings: Any, storage: Any, review: ExpiryReview) -> ReviewDetail:
    plants = expiry.outlook(storage, review.run_id)
    return ReviewDetail(
        review=_review_out(db, settings, review),
        items=[_item_out(i) for i in _items(db, review)],
        outlook=[
            PlantOutlook(
                plant=str(p),
                plant_name=str(n or ""),
                expired=float(e),
                within_3_months=float(w),
                three_to_6_months=float(s),
            )
            for p, n, e, w, s in plants.itertuples(index=False)
        ],
        root_causes=expiry.ROOT_CAUSES,
        measures=expiry.MEASURES,
    )


def _review(db: Any, review_id: int) -> ExpiryReview:
    review = db.get(ExpiryReview, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Follow-up not found.")
    return review  # type: ignore[no-any-return]


def _justify(
    db: Any, review: ExpiryReview, item_id: int, body: Justification, now: datetime
) -> ExpiryJustification:
    item = db.get(ExpiryJustification, item_id)
    if item is None or item.review_id != review.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found.")
    try:
        expiry.justify(item, body.root_cause, body.reason, body.justified_by, now)
    except expiry.JustificationError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    return item  # type: ignore[no-any-return]


@admin_router.get("", response_model=Overview)
def overview(_: CurrentUserDep, db: DbDep, settings: SettingsDep) -> Overview:
    runs = db.scalars(
        select(AnalysisRun)
        .where(AnalysisRun.analysis_key == expiry.ANALYSIS_KEY, AnalysisRun.status == "succeeded")
        .order_by(AnalysisRun.id.desc())
    ).all()
    reviews = {
        r.run_id: r
        for r in db.scalars(
            select(ExpiryReview).where(ExpiryReview.run_id.in_([run.id for run in runs]))
        )
    }
    return Overview(
        runs=[
            RunRow(
                run_id=run.id,
                label=run.label,
                opening_date=str(run.parameters.get("opening_date", "")),
                closing_date=str(run.parameters.get("closing_date", "")),
                created_at=run.created_at,
                review=_review_out(db, settings, reviews[run.id]) if run.id in reviews else None,
            )
            for run in runs
        ],
        mail_ready=ready(settings),
        root_causes=expiry.ROOT_CAUSES,
        measures=expiry.MEASURES,
    )


@admin_router.post("/runs/{run_id}", response_model=ReviewDetail)
def prepare(
    run_id: int,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    storage: StorageDep,
) -> ReviewDetail:
    run = db.get(AnalysisRun, run_id)
    if run is None or run.analysis_key != expiry.ANALYSIS_KEY or run.status != "succeeded":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expiry monitoring run not found.")
    review = expiry.ensure_review(db, storage, run)
    audit.record(
        db,
        "expiry.review_prepared",
        user_id=current.user.id,
        ip_address=client_ip(request),
        run=run.id,
        review=review.id,
    )
    db.commit()
    return _detail(db, settings, storage, review)


@admin_router.get("/reviews/{review_id}", response_model=ReviewDetail)
def read_review(
    review_id: int, _: CurrentUserDep, db: DbDep, settings: SettingsDep, storage: StorageDep
) -> ReviewDetail:
    return _detail(db, settings, storage, _review(db, review_id))


@admin_router.patch("/reviews/{review_id}/items/{item_id}", response_model=ItemOut)
def admin_justify(
    review_id: int,
    item_id: int,
    body: Justification,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    now: NowDep,
) -> ItemOut:
    item = _justify(db, _review(db, review_id), item_id, body, now)
    audit.record(
        db,
        "expiry.justified",
        user_id=current.user.id,
        ip_address=client_ip(request),
        item=item.id,
        root_cause=item.root_cause,
    )
    db.commit()
    return _item_out(item)


@admin_router.post("/reviews/{review_id}/send", status_code=status.HTTP_202_ACCEPTED)
def send(
    review_id: int,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    queue: QueueDep,
) -> dict[str, str]:
    review = _review(db, review_id)
    if not ready(settings):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "E-mail is not set up: SMTP and EXPIRY_MAIL_TO must be set on the server.",
        )
    queue.enqueue(send_now, review.id)
    audit.record(
        db,
        "expiry.mail_sent",
        user_id=current.user.id,
        ip_address=client_ip(request),
        review=review.id,
    )
    db.commit()
    return {"status": "queued"}


@admin_router.get("/reviews/{review_id}/justifications.xlsx")
def justifications_workbook(review_id: int, _: CurrentUserDep, db: DbDep) -> Response:
    review = _review(db, review_id)
    return Response(
        expiry.justification_workbook(review, _items(db, review)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="Expiry_justifications_{review.closing_date}.xlsx"'
            ),
            "Cache-Control": "private, no-store",
        },
    )


@admin_router.get("/reviews/{review_id}/justifications.html")
def justifications_dashboard(review_id: int, _: CurrentUserDep, db: DbDep) -> Response:
    review = _review(db, review_id)
    return Response(
        expiry.justification_dashboard(review, _items(db, review)),
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="Expiry_justifications_{review.closing_date}.html"'
            ),
            "Cache-Control": "private, no-store",
        },
    )


# --- The secure link ------------------------------------------------------------------------


def _by_token(db: Any, token: str) -> ExpiryReview:
    review = db.scalar(select(ExpiryReview).where(ExpiryReview.token == token))
    if review is None or len(token) < 20:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link is not valid.")
    return review  # type: ignore[no-any-return]


@public_router.get("/{token}", response_model=ReviewDetail)
def public_review(
    token: str, db: DbDep, settings: SettingsDep, storage: StorageDep
) -> ReviewDetail:
    detail = _detail(db, settings, storage, _by_token(db, token))
    detail.review.link = ""  # the person already has it
    return detail


@public_router.post("/{token}/items/{item_id}", response_model=ItemOut)
def public_justify(
    token: str, item_id: int, body: Justification, request: Request, db: DbDep, now: NowDep
) -> ItemOut:
    item = _justify(db, _by_token(db, token), item_id, body, now)
    audit.record(
        db,
        "expiry.justified",
        ip_address=client_ip(request),
        item=item.id,
        root_cause=item.root_cause,
        by=item.justified_by,
        via="link",
    )
    db.commit()
    return _item_out(item)
