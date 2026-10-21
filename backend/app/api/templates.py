"""Admin: organisation templates for Word and PowerPoint reports."""

import io
import zipfile

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select, update

from app.api.deps import CurrentUserDep, DbDep, client_ip
from app.api.uploads import StorageDep
from app.core import audit
from app.db.models import ReportTemplate
from app.storage import TooLargeError
from app.storage.filetypes import safe_filename

router = APIRouter(prefix="/api/admin/templates", tags=["admin templates"])

MAX_TEMPLATE_BYTES = 30 * 1024 * 1024


class TemplateOut(BaseModel):
    id: int
    kind: str
    name: str
    filename: str
    active: bool
    created_at: str


def _out(template: ReportTemplate) -> TemplateOut:
    return TemplateOut(
        id=template.id,
        kind=template.kind,
        name=template.name,
        filename=template.filename,
        active=template.active,
        created_at=template.created_at.isoformat(),
    )


def office_kind(content: bytes) -> str | None:
    """'docx' or 'pptx' from the package contents (templates .dotx/.potx included)."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as package:
            types = package.read("[Content_Types].xml").decode("utf-8", errors="replace")
    except (zipfile.BadZipFile, KeyError):
        return None
    if "wordprocessingml" in types:
        return "docx"
    if "presentationml" in types:
        return "pptx"
    return None


@router.get("", response_model=list[TemplateOut])
def list_templates(_: CurrentUserDep, db: DbDep) -> list[TemplateOut]:
    rows = db.scalars(select(ReportTemplate).order_by(ReportTemplate.id.desc())).all()
    return [_out(t) for t in rows]


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def upload_template(
    file: UploadFile,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    storage: StorageDep,
) -> TemplateOut:
    content = file.file.read(MAX_TEMPLATE_BYTES + 1)
    if len(content) > MAX_TEMPLATE_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The template is larger than 30 MB.")
    kind = office_kind(content)
    if kind is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Upload a Word (.docx) or PowerPoint (.pptx) template.",
        )
    try:
        key, _, _ = storage.save(io.BytesIO(content), MAX_TEMPLATE_BYTES, prefix="templates")
    except TooLargeError:  # pragma: no cover - checked above
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Too large.") from None
    filename = safe_filename(file.filename or f"template.{kind}", fallback=f"template.{kind}")
    template = ReportTemplate(
        kind=kind,
        name=filename.rsplit(".", 1)[0],
        filename=filename,
        storage_key=key,
        active=False,
    )
    db.add(template)
    db.flush()
    audit.record(
        db,
        "template.uploaded",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=template.id,
        filename=filename,
    )
    db.commit()
    return _out(template)


@router.post("/{template_id}/activate", response_model=TemplateOut)
def activate_template(
    template_id: int, request: Request, current: CurrentUserDep, db: DbDep
) -> TemplateOut:
    template = db.get(ReportTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found.")
    db.execute(
        update(ReportTemplate).where(ReportTemplate.kind == template.kind).values(active=False)
    )
    template.active = True
    audit.record(
        db,
        "template.activated",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=template_id,
    )
    db.commit()
    return _out(template)


@router.post("/{template_id}/deactivate", response_model=TemplateOut)
def deactivate_template(template_id: int, _: CurrentUserDep, db: DbDep) -> TemplateOut:
    template = db.get(ReportTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found.")
    template.active = False
    db.commit()
    return _out(template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: int, request: Request, current: CurrentUserDep, db: DbDep, storage: StorageDep
) -> None:
    template = db.get(ReportTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template not found.")
    storage.delete(template.storage_key)
    db.delete(template)
    audit.record(
        db,
        "template.deleted",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=template_id,
    )
    db.commit()
