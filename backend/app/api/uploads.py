"""Admin: upload data files in chunks (resumable), list and delete them."""

import hashlib
import secrets
import shutil
from collections import Counter
from datetime import timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from rq import Queue
from sqlalchemy import delete, select

from app.api.deps import CurrentUserDep, DbDep, NowDep, SettingsDep, client_ip
from app.core import audit
from app.db.models import AnalysisRun, DataFile, UploadSession
from app.ingest.parse import detect_format
from app.jobs.ingest import parse_data_file, parsed_dir_key
from app.jobs.queue import get_queue
from app.storage import LocalStorage, get_storage
from app.storage.filetypes import safe_filename

CHUNK_SIZE = 8 * 1024 * 1024
SESSION_LIFETIME = timedelta(hours=24)
ALLOWED_SUFFIXES = (".xlsx", ".xlsm", ".xls", ".csv", ".txt")

StorageDep = Annotated[LocalStorage, Depends(get_storage)]


def get_job_queue() -> Queue:
    return get_queue()


QueueDep = Annotated[Queue, Depends(get_job_queue)]

router = APIRouter(prefix="/api/admin", tags=["admin data"])


class UploadStart(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)


class UploadState(BaseModel):
    id: str
    filename: str
    size_bytes: int
    chunk_size: int
    chunk_count: int
    received_chunks: list[int]


class DataFileOut(BaseModel):
    id: int
    filename: str
    size_bytes: int
    sha256: str
    status: str
    message: str
    sheets: list[dict[str, Any]]
    created_at: str
    used_by_runs: int = 0
    source: str = "upload"
    source_path: str | None = None


def _chunk_count(size: int, chunk_size: int) -> int:
    return (size + chunk_size - 1) // chunk_size


def _state(session: UploadSession) -> UploadState:
    return UploadState(
        id=session.id,
        filename=session.filename,
        size_bytes=session.size_bytes,
        chunk_size=session.chunk_size,
        chunk_count=_chunk_count(session.size_bytes, session.chunk_size),
        received_chunks=sorted(session.received_chunks or []),
    )


def _session(db: DbDep, upload_id: str) -> UploadSession:
    session = db.get(UploadSession, upload_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found or expired.")
    return session


@router.post("/uploads", response_model=UploadState, status_code=status.HTTP_201_CREATED)
def start_upload(
    body: UploadStart,
    _: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    storage: StorageDep,
    now: NowDep,
) -> UploadState:
    name = safe_filename(body.filename, fallback="upload")
    if not name.lower().endswith(ALLOWED_SUFFIXES):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "Upload Excel (.xlsx, .xls) or CSV files exported from SAP.",
        )
    max_bytes = settings.data_upload_max_mb * 1024 * 1024
    if body.size_bytes > max_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"The file is larger than {settings.data_upload_max_mb} MB.",
        )
    # Forget uploads that were abandoned long ago.
    for old in db.scalars(
        select(UploadSession).where(UploadSession.created_at < now - SESSION_LIFETIME)
    ):
        shutil.rmtree(storage.path(f"uploads/{old.id}"), ignore_errors=True)
        db.delete(old)
    session = UploadSession(
        id=secrets.token_hex(16),
        filename=name,
        size_bytes=body.size_bytes,
        chunk_size=CHUNK_SIZE,
        received_chunks=[],
        created_at=now,
    )
    db.add(session)
    db.commit()
    return _state(session)


@router.get("/uploads/{upload_id}", response_model=UploadState)
def upload_state(upload_id: str, _: CurrentUserDep, db: DbDep) -> UploadState:
    return _state(_session(db, upload_id))


@router.put("/uploads/{upload_id}/chunks/{index}", status_code=status.HTTP_204_NO_CONTENT)
async def upload_chunk(
    upload_id: str,
    index: int,
    request: Request,
    _: CurrentUserDep,
    db: DbDep,
    storage: StorageDep,
) -> None:
    session = _session(db, upload_id)
    count = _chunk_count(session.size_bytes, session.chunk_size)
    if not 0 <= index < count:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chunk number out of range.")
    expected = (
        session.chunk_size if index < count - 1 else session.size_bytes - index * session.chunk_size
    )
    target = storage.path(f"uploads/{upload_id}/{index}")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    received = 0
    with open(partial, "wb") as out:
        async for piece in request.stream():
            received += len(piece)
            if received > expected:
                out.close()
                partial.unlink(missing_ok=True)
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chunk larger than expected.")
            out.write(piece)
    if received != expected:
        partial.unlink(missing_ok=True)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Chunk {index} has {received} bytes; {expected} were expected.",
        )
    partial.replace(target)
    db.refresh(session)
    session.received_chunks = sorted({*(session.received_chunks or []), index})
    db.commit()


@router.post(
    "/uploads/{upload_id}/complete",
    response_model=DataFileOut,
    status_code=status.HTTP_201_CREATED,
)
def complete_upload(
    upload_id: str,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    storage: StorageDep,
    queue: QueueDep,
) -> DataFileOut:
    session = _session(db, upload_id)
    count = _chunk_count(session.size_bytes, session.chunk_size)
    missing = sorted(set(range(count)) - set(session.received_chunks or []))
    if missing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{len(missing)} chunk(s) are still missing.")
    key = f"data/{secrets.token_hex(16)}"
    target = storage.path(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with open(target, "wb") as out:
        for index in range(count):
            with open(storage.path(f"uploads/{upload_id}/{index}"), "rb") as chunk:
                while block := chunk.read(1024 * 1024):
                    digest.update(block)
                    out.write(block)
    shutil.rmtree(storage.path(f"uploads/{upload_id}"), ignore_errors=True)
    db.delete(session)

    with open(target, "rb") as handle:
        if detect_format(handle.read(4096)) is None:
            target.unlink(missing_ok=True)
            db.commit()
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                "This file is not an Excel or CSV file.",
            )
    data_file = DataFile(
        filename=session.filename,
        size_bytes=session.size_bytes,
        sha256=digest.hexdigest(),
        storage_key=key,
        status="received",
        message="Waiting to be read",
        sheets=[],
    )
    db.add(data_file)
    db.flush()
    audit.record(
        db,
        "data.uploaded",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=data_file.id,
        filename=data_file.filename,
        size_bytes=data_file.size_bytes,
    )
    db.commit()
    queue.enqueue(parse_data_file, data_file.id, job_timeout=3600)
    db.refresh(data_file)
    return _out(db, data_file)


def _usage(db: DbDep) -> Counter[int]:
    """How many runs used each data file (read once, not once per file)."""
    used: Counter[int] = Counter()
    all_inputs: list[dict[str, Any] | None] = list(db.scalars(select(AnalysisRun.inputs)))
    for inputs in all_inputs:
        ids = {choice.get("data_file_id") for choice in (inputs or {}).values()}
        ids |= {
            extra.get("data_file_id")
            for choice in (inputs or {}).values()
            for extra in choice.get("more", [])
        }
        used.update(i for i in ids if isinstance(i, int))
    return used


def _out(db: DbDep, data_file: DataFile, usage: Counter[int] | None = None) -> DataFileOut:
    used = (usage if usage is not None else _usage(db))[data_file.id]
    return DataFileOut(
        id=data_file.id,
        source=data_file.source,
        source_path=data_file.source_path,
        filename=data_file.filename,
        size_bytes=data_file.size_bytes,
        sha256=data_file.sha256,
        status=data_file.status,
        message=data_file.message,
        sheets=data_file.sheets or [],
        created_at=data_file.created_at.isoformat(),
        used_by_runs=used,
    )


@router.get("/data-files", response_model=list[DataFileOut])
def list_data_files(_: CurrentUserDep, db: DbDep) -> list[DataFileOut]:
    files = db.scalars(select(DataFile).order_by(DataFile.id.desc())).all()
    usage = _usage(db)
    return [_out(db, f, usage) for f in files]


@router.get("/data-files/{file_id}", response_model=DataFileOut)
def read_data_file(file_id: int, _: CurrentUserDep, db: DbDep) -> DataFileOut:
    data_file = db.get(DataFile, file_id)
    if data_file is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    return _out(db, data_file)


@router.delete("/data-files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_data_file(
    file_id: int,
    request: Request,
    current: CurrentUserDep,
    db: DbDep,
    storage: StorageDep,
) -> None:
    data_file = db.get(DataFile, file_id)
    if data_file is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    shutil.rmtree(storage.path(parsed_dir_key(data_file)), ignore_errors=True)
    storage.delete(data_file.storage_key)
    db.execute(delete(DataFile).where(DataFile.id == file_id))
    audit.record(
        db,
        "data.deleted",
        user_id=current.user.id,
        ip_address=client_ip(request),
        id=file_id,
        filename=data_file.filename,
    )
    db.commit()
