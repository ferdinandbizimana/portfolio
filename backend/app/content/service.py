"""Reading and writing portfolio content."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content.schemas import (
    Credential,
    ExperienceOut,
    FileRef,
    Highlight,
    ProfileOut,
    ProjectOut,
    ProjectSummaryOut,
    SkillGroupOut,
)
from app.db.models import ExperienceEntry, Profile, Project, SkillGroup, StoredFile

DEFAULT_NAME = "Ferdinand Bizimana"
DEFAULT_HEADLINE = "Supply chain professional · SAP S/4HANA (MM, EWM, SD, FI)"


def file_url(file: StoredFile) -> str:
    return f"/api/public/files/{file.id}/{file.filename}"


def file_ref(db: Session, file_id: int | None) -> FileRef | None:
    if file_id is None:
        return None
    file = db.get(StoredFile, file_id)
    if file is None:
        return None
    return FileRef(
        id=file.id, filename=file.filename, content_type=file.content_type, url=file_url(file)
    )


def get_profile(db: Session) -> Profile:
    """The single profile row, created with defaults the first time."""
    profile = db.get(Profile, 1)
    if profile is None:
        profile = Profile(id=1, full_name=DEFAULT_NAME, headline=DEFAULT_HEADLINE)
        db.add(profile)
        db.commit()
    return profile


def profile_out(db: Session, profile: Profile) -> ProfileOut:
    return ProfileOut(
        full_name=profile.full_name,
        headline=profile.headline,
        location=profile.location,
        summary_md=profile.summary_md,
        about_md=profile.about_md,
        linkedin_url=profile.linkedin_url,
        github_url=profile.github_url,
        photo=file_ref(db, profile.photo_file_id),
        cv=file_ref(db, profile.cv_file_id),
        availability=profile.availability or "",
        highlights=[Highlight(**h) for h in profile.highlights or []],
        certifications=[Credential(**c) for c in profile.certifications or []],
        education=[Credential(**c) for c in profile.education or []],
        languages=list(profile.languages or []),
    )


def experience_out(entry: ExperienceEntry) -> ExperienceOut:
    return ExperienceOut(
        id=entry.id,
        role=entry.role,
        organisation=entry.organisation,
        location=entry.location,
        start_month=entry.start_month,
        end_month=entry.end_month,
        description_md=entry.description_md,
    )


def skill_group_out(group: SkillGroup) -> SkillGroupOut:
    return SkillGroupOut(id=group.id, name=group.name, items=list(group.items or []))


def project_summary_out(db: Session, project: Project) -> ProjectSummaryOut:
    return ProjectSummaryOut(
        id=project.id,
        slug=project.slug,
        title=project.title,
        summary=project.summary,
        tags=list(project.tags or []),
        cover=file_ref(db, project.cover_file_id),
        published=project.published,
        featured=project.featured,
    )


def project_out(db: Session, project: Project) -> ProjectOut:
    summary = project_summary_out(db, project)
    return ProjectOut(
        **summary.model_dump(), body_md=project.body_md, cover_file_id=project.cover_file_id
    )


def experience_entries(db: Session) -> Sequence[ExperienceEntry]:
    # Manual order first; within equal order, the most recent role first.
    return db.scalars(
        select(ExperienceEntry).order_by(
            ExperienceEntry.sort_order,
            ExperienceEntry.start_month.desc(),
            ExperienceEntry.id,
        )
    ).all()


def skill_groups(db: Session) -> Sequence[SkillGroup]:
    return db.scalars(select(SkillGroup).order_by(SkillGroup.sort_order, SkillGroup.id)).all()


def projects(db: Session, published_only: bool) -> Sequence[Project]:
    query = select(Project).order_by(Project.sort_order, Project.id)
    if published_only:
        query = query.where(Project.published.is_(True))
    return db.scalars(query).all()


def reorder[M: (ExperienceEntry, SkillGroup, Project)](
    db: Session, model: type[M], ids: list[int]
) -> bool:
    """Set sort_order from the given id order. False if the ids do not match the rows."""
    rows = {row.id: row for row in db.scalars(select(model)).all()}
    if sorted(ids) != sorted(rows):
        return False
    for position, row_id in enumerate(ids):
        rows[row_id].sort_order = position
    return True


def next_sort_order[M: (ExperienceEntry, SkillGroup, Project)](db: Session, model: type[M]) -> int:
    rows = db.scalars(select(model.sort_order)).all()
    return max(rows, default=-1) + 1


def existing_file_id(db: Session, file_id: int | None) -> bool:
    return file_id is None or db.get(StoredFile, file_id) is not None
