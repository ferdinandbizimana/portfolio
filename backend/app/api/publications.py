"""Publishing dashboards: private, secret link or public, and unpublishing.

Admin routes create and manage publications. Public routes return only the
frozen snapshot and its title and description: never run ids, file names,
input fingerprints or anything else from the private side.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep, NowDep, client_ip
from app.core import audit
from app.db.models import AnalysisRun, Publication
from app.publishing import DetailLevel, build_snapshot, new_token, slug_base

Visibility = Literal["private", "secret", "public"]

admin_router = APIRouter(prefix="/api/admin", tags=["admin publishing"])
public_router = APIRouter(prefix="/api/public", tags=["public"])


class PublicationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    detail_level: DetailLevel = "summary"
    include_checks: bool = False


class PublicationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    visibility: Visibility | None = None


class PublicationOut(BaseModel):
    id: int
    run_id: int | None
    slug: str
    secret_token: str
    visibility: Visibility
    title: str
    description: str
    detail_level: DetailLevel
    include_checks: bool
    snapshot: dict[str, Any]
    created_at: datetime
    published_at: datetime | None


class PublicDashboard(BaseModel):
    """What visitors receive. Deliberately small."""

    slug: str
    title: str
    description: str
    published_at: datetime | None
    dashboard: dict[str, Any]


class PublicListItem(BaseModel):
    slug: str
    title: str
    description: str
    published_at: datetime | None


def _out(publication: Publication) -> PublicationOut:
    return PublicationOut(
        id=publication.id,
        run_id=publication.run_id,
        slug=publication.slug,
        secret_token=publication.secret_token,
        visibility=publication.visibility,
        title=publication.title,
        description=publication.description,
        detail_level=publication.detail_level,
        include_checks=publication.include_checks,
        snapshot=publication.snapshot,
        created_at=publication.created_at,
        published_at=publication.published_at,
    )


def _finished_run(db: DbDep, run_id: int) -> tuple[AnalysisRun, dict[str, Any]]:
    run = db.get(AnalysisRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Run not found.")
    if run.status != "succeeded" or not run.dashboard:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Only a finished run with a dashboard can be published."
        )
    return run, run.dashboard


def _unique_slug(db: DbDep, title: str) -> str:
    base = slug_base(title)
    slug, n = base, 2
    while db.scalar(select(Publication.id).where(Publication.slug == slug)) is not None:
        slug = f"{base}-{n}"
        n += 1
    return slug


@admin_router.get("/runs/{run_id}/publication-preview")
def preview(
    run_id: int,
    _: CurrentUserDep,
    db: DbDep,
    detail_level: Annotated[DetailLevel, Query()] = "summary",
    include_checks: Annotated[bool, Query()] = False,
) -> dict[str, Any]:
    """Exactly what visitors would see."""
    dashboard = _finished_run(db, run_id)[1]
    return build_snapshot(dashboard, detail_level, include_checks)


@admin_router.post(
    "/runs/{run_id}/publications",
    response_model=PublicationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_publication(
    run_id: int, body: PublicationCreate, request: Request, current: CurrentUserDep, db: DbDep
) -> PublicationOut:
    run, dashboard = _finished_run(db, run_id)
    publication = Publication(
        run_id=run.id,
        slug=_unique_slug(db, body.title),
        secret_token=new_token(),
        visibility="private",
        title=body.title.strip(),
        description=body.description.strip(),
        detail_level=body.detail_level,
        include_checks=body.include_checks,
        snapshot=build_snapshot(dashboard, body.detail_level, body.include_checks),
    )
    db.add(publication)
    db.flush()
    audit.record(
        db,
        "publication.created",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=publication.id,
        run_id=run.id,
        detail_level=body.detail_level,
    )
    db.commit()
    return _out(publication)


@admin_router.get("/publications", response_model=list[PublicationOut])
def list_publications(_: CurrentUserDep, db: DbDep) -> list[PublicationOut]:
    rows = db.scalars(select(Publication).order_by(Publication.id.desc())).all()
    return [_out(p) for p in rows]


def _publication(db: DbDep, publication_id: int) -> Publication:
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Publication not found.")
    return publication


@admin_router.get("/publications/{publication_id}", response_model=PublicationOut)
def read_publication(publication_id: int, _: CurrentUserDep, db: DbDep) -> PublicationOut:
    return _out(_publication(db, publication_id))


@admin_router.patch("/publications/{publication_id}", response_model=PublicationOut)
def update_publication(
    publication_id: int,
    body: PublicationUpdate,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    now: NowDep,
) -> PublicationOut:
    publication = _publication(db, publication_id)
    if body.title is not None:
        publication.title = body.title.strip()
    if body.description is not None:
        publication.description = body.description.strip()
    if body.visibility is not None and body.visibility != publication.visibility:
        previous = publication.visibility
        publication.visibility = body.visibility
        if body.visibility == "public" and publication.published_at is None:
            publication.published_at = now
        audit.record(
            db,
            "publication.visibility_changed",
            user_id=current.user.id,
            ip_address=client_ip(request),
            id=publication.id,
            visibility_from=previous,
            visibility_to=body.visibility,
        )
    db.commit()
    return _out(publication)


@admin_router.post("/publications/{publication_id}/new-link", response_model=PublicationOut)
def renew_secret_link(
    publication_id: int, request: Request, current: CurrentUserDep, db: DbDep
) -> PublicationOut:
    """Replace the secret link; the old one stops working at once."""
    publication = _publication(db, publication_id)
    publication.secret_token = new_token()
    audit.record(
        db,
        "publication.link_renewed",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=publication.id,
    )
    db.commit()
    return _out(publication)


@admin_router.delete("/publications/{publication_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_publication(
    publication_id: int, request: Request, current: CurrentUserDep, db: DbDep
) -> None:
    publication = _publication(db, publication_id)
    db.delete(publication)
    audit.record(
        db,
        "publication.deleted",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=publication_id,
    )
    db.commit()


def _public(publication: Publication) -> PublicDashboard:
    return PublicDashboard(
        slug=publication.slug,
        title=publication.title,
        description=publication.description,
        published_at=publication.published_at,
        dashboard=publication.snapshot,
    )


@public_router.get("/dashboards", response_model=list[PublicListItem])
def public_dashboards(db: DbDep) -> list[PublicListItem]:
    rows = db.scalars(
        select(Publication)
        .where(Publication.visibility == "public")
        .order_by(Publication.published_at.desc(), Publication.id.desc())
    ).all()
    return [
        PublicListItem(
            slug=p.slug, title=p.title, description=p.description, published_at=p.published_at
        )
        for p in rows
    ]


@public_router.get("/dashboards/{slug}", response_model=PublicDashboard)
def public_dashboard(slug: str, db: DbDep) -> PublicDashboard:
    publication = db.scalar(
        select(Publication).where(Publication.slug == slug, Publication.visibility == "public")
    )
    if publication is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dashboard not found.")
    return _public(publication)


@public_router.get("/shared/{token}", response_model=PublicDashboard)
def shared_dashboard(token: str, db: DbDep) -> PublicDashboard:
    publication = db.scalar(
        select(Publication).where(
            Publication.secret_token == token, Publication.visibility.in_(("secret", "public"))
        )
    )
    if publication is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dashboard not found.")
    return _public(publication)
