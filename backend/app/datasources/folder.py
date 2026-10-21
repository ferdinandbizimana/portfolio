"""Picking up SAP exports from a shared folder.

The folder is only read, never changed. A file is taken once it has stopped
changing for `settle_seconds`; it is copied into storage and read like an
upload. A file is taken again only when its size or modification time changes
and its content is different.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from rq import Queue
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import audit
from app.db.models import DataFile
from app.ingest.parse import detect_format
from app.jobs.ingest import parse_data_file
from app.storage import LocalStorage, TooLargeError

logger = logging.getLogger(__name__)

SOURCE = "folder"
# Storage key of a record whose file was not kept (deleting it is harmless).
NO_CONTENT_KEY = "data/not-kept"
EXTENSIONS = {".xlsx", ".xlsm", ".xls", ".csv", ".txt"}


@dataclass
class ScanResult:
    imported: list[DataFile] = field(default_factory=list)
    waiting: list[str] = field(default_factory=list)  # still being written
    unchanged: int = 0


def _candidates(root: Path) -> list[Path]:
    files = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part.startswith((".", "~$")) for part in relative.parts):
            continue  # hidden files and Office lock files
        if path.suffix.lower() in EXTENSIONS and path.is_file():
            files.append(path)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def _latest(db: Session, relative: str) -> DataFile | None:
    return db.scalar(
        select(DataFile)
        .where(DataFile.source == SOURCE, DataFile.source_path == relative)
        .order_by(DataFile.id.desc())
        .limit(1)
    )


def scan_folder(
    db: Session,
    storage: LocalStorage,
    queue: Queue,
    root: Path,
    *,
    now: float,
    settle_seconds: int,
    max_bytes: int,
) -> ScanResult:
    """Import new or changed files from `root`. `now` is a Unix timestamp."""
    result = ScanResult()
    if not root.is_dir():
        logger.warning("Shared folder %s does not exist or is not a folder", root)
        return result
    for path in _candidates(root):
        relative = path.relative_to(root).as_posix()
        try:
            stat = path.stat()
        except OSError:
            continue  # removed while scanning
        if now - stat.st_mtime < settle_seconds:
            result.waiting.append(relative)
            continue
        previous = _latest(db, relative)
        if (
            previous is not None
            and previous.size_bytes == stat.st_size
            and previous.source_mtime_ns == stat.st_mtime_ns
        ):
            result.unchanged += 1
            continue
        data_file = _import(db, storage, path, relative, stat.st_mtime_ns, max_bytes, previous)
        if data_file is None:
            result.unchanged += 1
            continue
        result.imported.append(data_file)
        if data_file.status == "received":
            queue.enqueue(parse_data_file, data_file.id, job_timeout=3600)
    return result


def _import(
    db: Session,
    storage: LocalStorage,
    path: Path,
    relative: str,
    mtime_ns: int,
    max_bytes: int,
    previous: DataFile | None,
) -> DataFile | None:
    data_file = DataFile(
        filename=path.name[:255],
        source=SOURCE,
        source_path=relative,
        source_mtime_ns=mtime_ns,
        sheets=[],
    )
    try:
        with open(path, "rb") as handle:
            key, size, sha256 = storage.save(handle, max_bytes, "data")
    except TooLargeError:
        data_file.storage_key, data_file.sha256 = NO_CONTENT_KEY, ""
        data_file.size_bytes = path.stat().st_size
        data_file.status = "failed"
        data_file.message = f"The file is larger than the limit of {max_bytes // 2**20} MB."
    except OSError as error:
        logger.warning("Could not read %s from the shared folder: %s", relative, error)
        return None
    else:
        if previous is not None and previous.sha256 == sha256:
            # Touched but not changed: remember the new time, keep the old record.
            storage.delete(key)
            previous.source_mtime_ns = mtime_ns
            db.commit()
            return None
        data_file.storage_key, data_file.size_bytes, data_file.sha256 = key, size, sha256
        with storage.open(key) as handle:
            known = detect_format(handle.read(4096)) is not None
        if known:
            data_file.status = "received"
            data_file.message = "Waiting to be read"
        else:
            storage.delete(key)
            data_file.status = "failed"
            data_file.message = "This file is not an Excel or CSV file."
    db.add(data_file)
    db.flush()
    audit.record(
        db,
        "data.picked_up",
        id=data_file.id,
        path=relative,
        size_bytes=data_file.size_bytes,
        status=data_file.status,
    )
    db.commit()
    return data_file
