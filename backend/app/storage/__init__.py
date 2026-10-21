"""File storage behind a small interface, so the backend can change (e.g. to S3) later."""

import hashlib
import os
import secrets
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO, Protocol

from app.core.config import get_settings

CHUNK_SIZE = 1024 * 1024


class Storage(Protocol):
    def save(self, stream: BinaryIO, max_bytes: int, prefix: str) -> tuple[str, int, str]:
        """Store the stream. Return (key, size in bytes, SHA-256). Raise TooLarge."""
        ...

    def open(self, key: str) -> BinaryIO: ...

    def path(self, key: str) -> Path: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...


class TooLargeError(Exception):
    pass


class LocalStorage:
    """Files on a local directory (a Docker volume in production)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def path(self, key: str) -> Path:
        resolved = (self.root / key).resolve()
        if self.root.resolve() not in resolved.parents:
            raise ValueError(f"Invalid storage key: {key}")
        return resolved

    def save(self, stream: BinaryIO, max_bytes: int, prefix: str) -> tuple[str, int, str]:
        key = f"{prefix}/{secrets.token_hex(16)}"
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        partial = target.with_suffix(".part")
        try:
            with open(partial, "wb") as out:
                for chunk in _chunks(stream):
                    size += len(chunk)
                    if size > max_bytes:
                        raise TooLargeError
                    digest.update(chunk)
                    out.write(chunk)
            os.replace(partial, target)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        return key, size, digest.hexdigest()

    def open(self, key: str) -> BinaryIO:
        return open(self.path(key), "rb")

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()


def _chunks(stream: BinaryIO) -> Iterator[bytes]:
    while chunk := stream.read(CHUNK_SIZE):
        yield chunk


def get_storage() -> LocalStorage:
    return LocalStorage(get_settings().storage_dir)
