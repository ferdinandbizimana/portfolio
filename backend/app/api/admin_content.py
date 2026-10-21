"""Admin: edit portfolio content."""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep, client_ip
from app.content import service
from app.content.schemas import (
    ExperienceIn,
    ExperienceOut,
    ProfileIn,
    ProfileOut,
    ProjectIn,
    ProjectOut,
    ProjectSummaryOut,
    ReorderIn,
    SkillGroupIn,
    SkillGroupOut,
)
from app.core import audit
from app.db.models import ExperienceEntry, Project, SkillGroup

router = APIRouter(prefix="/api/admin/content", tags=["admin content"])


def _check_files(db: DbDep, *file_ids: int | None) -> None:
    for file_id in file_ids:
        if not service.existing_file_id(db, file_id):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"File {file_id} does not exist.")


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found.")


# ---------------------------------------------------------------- profile


@router.get("/profile", response_model=ProfileOut)
def read_profile(_: CurrentUserDep, db: DbDep) -> ProfileOut:
    return service.profile_out(db, service.get_profile(db))


@router.put("/profile", response_model=ProfileOut)
def update_profile(
    body: ProfileIn, request: Request, current: CurrentUserDep, db: DbDep
) -> ProfileOut:
    _check_files(db, body.photo_file_id, body.cv_file_id)
    profile = service.get_profile(db)
    for field, value in body.model_dump().items():
        setattr(profile, field, value)
    audit.record(
        db, "content.profile_updated", user_id=current.user.id, ip_address=client_ip(request)
    )
    db.commit()
    return service.profile_out(db, profile)


# ---------------------------------------------------------------- experience


@router.get("/experience", response_model=list[ExperienceOut])
def list_experience(_: CurrentUserDep, db: DbDep) -> list[ExperienceOut]:
    return [service.experience_out(e) for e in service.experience_entries(db)]


@router.post("/experience", response_model=ExperienceOut, status_code=status.HTTP_201_CREATED)
def create_experience(
    body: ExperienceIn, request: Request, current: CurrentUserDep, db: DbDep
) -> ExperienceOut:
    entry = ExperienceEntry(
        **body.model_dump(), sort_order=service.next_sort_order(db, ExperienceEntry)
    )
    db.add(entry)
    db.flush()
    audit.record(
        db,
        "content.experience_created",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=entry.id,
    )
    db.commit()
    return service.experience_out(entry)


@router.put("/experience/{entry_id}", response_model=ExperienceOut)
def update_experience(
    entry_id: int, body: ExperienceIn, request: Request, current: CurrentUserDep, db: DbDep
) -> ExperienceOut:
    entry = db.get(ExperienceEntry, entry_id)
    if entry is None:
        raise _not_found("Experience entry")
    for field, value in body.model_dump().items():
        setattr(entry, field, value)
    audit.record(
        db,
        "content.experience_updated",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=entry_id,
    )
    db.commit()
    return service.experience_out(entry)


@router.delete("/experience/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_experience(entry_id: int, request: Request, current: CurrentUserDep, db: DbDep) -> None:
    entry = db.get(ExperienceEntry, entry_id)
    if entry is None:
        raise _not_found("Experience entry")
    db.delete(entry)
    audit.record(
        db,
        "content.experience_deleted",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=entry_id,
    )
    db.commit()


@router.post("/experience/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_experience(body: ReorderIn, _: CurrentUserDep, db: DbDep) -> None:
    if not service.reorder(db, ExperienceEntry, body.ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The list of entries has changed.")
    db.commit()


# ---------------------------------------------------------------- skills


@router.get("/skills", response_model=list[SkillGroupOut])
def list_skills(_: CurrentUserDep, db: DbDep) -> list[SkillGroupOut]:
    return [service.skill_group_out(g) for g in service.skill_groups(db)]


@router.post("/skills", response_model=SkillGroupOut, status_code=status.HTTP_201_CREATED)
def create_skill_group(
    body: SkillGroupIn, request: Request, current: CurrentUserDep, db: DbDep
) -> SkillGroupOut:
    group = SkillGroup(**body.model_dump(), sort_order=service.next_sort_order(db, SkillGroup))
    db.add(group)
    db.flush()
    audit.record(
        db,
        "content.skills_created",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=group.id,
    )
    db.commit()
    return service.skill_group_out(group)


@router.put("/skills/{group_id}", response_model=SkillGroupOut)
def update_skill_group(
    group_id: int, body: SkillGroupIn, request: Request, current: CurrentUserDep, db: DbDep
) -> SkillGroupOut:
    group = db.get(SkillGroup, group_id)
    if group is None:
        raise _not_found("Skill group")
    group.name = body.name
    group.items = list(body.items)
    audit.record(
        db,
        "content.skills_updated",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=group_id,
    )
    db.commit()
    return service.skill_group_out(group)


@router.delete("/skills/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill_group(group_id: int, request: Request, current: CurrentUserDep, db: DbDep) -> None:
    group = db.get(SkillGroup, group_id)
    if group is None:
        raise _not_found("Skill group")
    db.delete(group)
    audit.record(
        db,
        "content.skills_deleted",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=group_id,
    )
    db.commit()


@router.post("/skills/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_skills(body: ReorderIn, _: CurrentUserDep, db: DbDep) -> None:
    if not service.reorder(db, SkillGroup, body.ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The list of groups has changed.")
    db.commit()


# ---------------------------------------------------------------- projects


@router.get("/projects", response_model=list[ProjectSummaryOut])
def list_projects(_: CurrentUserDep, db: DbDep) -> list[ProjectSummaryOut]:
    return [service.project_summary_out(db, p) for p in service.projects(db, published_only=False)]


def _slug_taken(db: DbDep, slug: str, except_id: int | None = None) -> bool:
    query = select(Project.id).where(Project.slug == slug)
    if except_id is not None:
        query = query.where(Project.id != except_id)
    return db.scalar(query) is not None


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    body: ProjectIn, request: Request, current: CurrentUserDep, db: DbDep
) -> ProjectOut:
    _check_files(db, body.cover_file_id)
    if _slug_taken(db, body.slug):
        raise HTTPException(status.HTTP_409_CONFLICT, "Another project already uses this slug.")
    project = Project(**body.model_dump(), sort_order=service.next_sort_order(db, Project))
    db.add(project)
    db.flush()
    audit.record(
        db,
        "content.project_created",
        user_id=current.user.id,
        ip_address=client_ip(request),
        slug=project.slug,
    )
    db.commit()
    return service.project_out(db, project)


@router.get("/projects/{project_id}", response_model=ProjectOut)
def read_project(project_id: int, _: CurrentUserDep, db: DbDep) -> ProjectOut:
    project = db.get(Project, project_id)
    if project is None:
        raise _not_found("Project")
    return service.project_out(db, project)


@router.put("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int, body: ProjectIn, request: Request, current: CurrentUserDep, db: DbDep
) -> ProjectOut:
    project = db.get(Project, project_id)
    if project is None:
        raise _not_found("Project")
    _check_files(db, body.cover_file_id)
    if _slug_taken(db, body.slug, except_id=project_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Another project already uses this slug.")
    for field, value in body.model_dump().items():
        setattr(project, field, value)
    audit.record(
        db,
        "content.project_updated",
        user_id=current.user.id,
        ip_address=client_ip(request),
        slug=project.slug,
        published=project.published,
    )
    db.commit()
    return service.project_out(db, project)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, request: Request, current: CurrentUserDep, db: DbDep) -> None:
    project = db.get(Project, project_id)
    if project is None:
        raise _not_found("Project")
    db.delete(project)
    audit.record(
        db,
        "content.project_deleted",
        user_id=current.user.id,
        ip_address=client_ip(request),
        slug=project.slug,
    )
    db.commit()


@router.post("/projects/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_projects(body: ReorderIn, _: CurrentUserDep, db: DbDep) -> None:
    if not service.reorder(db, Project, body.ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The list of projects has changed.")
    db.commit()
