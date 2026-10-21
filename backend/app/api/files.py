"""Portfolio files: upload (admin) and download (public)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import CurrentUserDep, DbDep, SettingsDep, client_ip
from app.content.schemas import FileRef
from app.content.service import file_url
from app.core import audit
from app.db.models import Profile, Project, StoredFile
from app.storage import LocalStorage, TooLargeError, get_storage
from app.storage.filetypes import safe_filename, sniff

StorageDep = Annotated[LocalStorage, Depends(get_storage)]

admin_router = APIRouter(prefix="/api/admin/files", tags=["admin files"])
public_router = APIRouter(prefix="/api/public/files", tags=["public"])


class StoredFileOut(FileRef):
    size_bytes: int


def _out(file: StoredFile) -> StoredFileOut:
    return StoredFileOut(
        id=file.id,
        filename=file.filename,
        content_type=file.content_type,
        url=file_url(file),
        size_bytes=file.size_bytes,
    )


@admin_router.post("", response_model=StoredFileOut, status_code=status.HTTP_201_CREATED)
def upload_file(
    file: UploadFile,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> StoredFileOut:
    """Upload a portfolio file (PNG, JPEG, WebP or PDF). Portfolio files are public."""
    content_type = sniff(file.file.read(16))
    file.file.seek(0)
    if content_type is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Only PNG, JPEG or WebP images and PDF documents can be uploaded here.",
        )
    max_mb = settings.content_file_max_mb
    try:
        key, size, digest = storage.save(file.file, max_mb * 1024 * 1024, prefix="content")
    except TooLargeError:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"The file is larger than {max_mb} MB."
        ) from None
    stored = StoredFile(
        storage_key=key,
        filename=safe_filename(file.filename or "", fallback="file"),
        content_type=content_type,
        size_bytes=size,
        sha256=digest,
        public=True,
    )
    db.add(stored)
    db.flush()
    audit.record(
        db,
        "content.file_uploaded",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=stored.id,
        filename=stored.filename,
    )
    db.commit()
    return _out(stored)


@admin_router.get("", response_model=list[StoredFileOut])
def list_files(_: CurrentUserDep, db: DbDep) -> list[StoredFileOut]:
    files = db.scalars(
        select(StoredFile).where(StoredFile.public.is_(True)).order_by(StoredFile.id.desc())
    ).all()
    return [_out(f) for f in files]


@admin_router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    file_id: int, request: Request, current: CurrentUserDep, db: DbDep, storage: StorageDep
) -> None:
    file = db.get(StoredFile, file_id)
    if file is None or not file.public:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    in_use = db.scalar(
        select(Profile.id).where(
            (Profile.photo_file_id == file_id) | (Profile.cv_file_id == file_id)
        )
    ) or db.scalar(select(Project.id).where(Project.cover_file_id == file_id))
    if in_use:
        raise HTTPException(status.HTTP_409_CONFLICT, "The file is still used by your content.")
    db.delete(file)
    audit.record(
        db,
        "content.file_deleted",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=file_id,
        filename=file.filename,
    )
    db.commit()
    storage.delete(file.storage_key)


@public_router.get("/{file_id}/{filename}")
def download_file(file_id: int, filename: str, db: DbDep, storage: StorageDep) -> FileResponse:
    file = db.get(StoredFile, file_id)
    if file is None or not file.public or not storage.exists(file.storage_key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    return FileResponse(
        storage.path(file.storage_key),
        media_type=file.content_type,
        filename=file.filename,
        content_disposition_type="attachment"
        if file.content_type == "application/pdf"
        else "inline",
        headers={
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "ETag": f'"{file.sha256}"',
        },
    )
