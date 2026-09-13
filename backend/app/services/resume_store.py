"""Private resume file storage.

Files live outside any public or static directory. A resume's database id is
the only on-disk identifier; the user-supplied filename is never used as a
filesystem path, only kept as metadata by the caller.
"""
import os
import uuid
from pathlib import Path

from app.core.config import get_settings


def storage_root() -> Path:
    return Path(get_settings().RESUME_STORAGE_DIR)


def file_path(storage_id: uuid.UUID) -> Path:
    return storage_root() / str(storage_id)


def ensure_storage_dir() -> Path:
    root = storage_root()
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise RuntimeError(f"Resume storage path is not a directory: {root}")
    return root


def write_bytes(storage_id: uuid.UUID, data: bytes) -> None:
    """Atomically write resume bytes. The destination is derived only from the
    server-generated storage id, never from submitted filenames."""
    root = ensure_storage_dir()
    destination = root / str(storage_id)
    temporary = root / f".{storage_id}.tmp-{uuid.uuid4().hex}"
    try:
        temporary.write_bytes(data)
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def delete_bytes(storage_id: uuid.UUID) -> None:
    try:
        file_path(storage_id).unlink(missing_ok=True)
    except OSError:
        pass


def read_bytes(storage_id: uuid.UUID) -> bytes | None:
    try:
        return file_path(storage_id).read_bytes()
    except FileNotFoundError:
        return None