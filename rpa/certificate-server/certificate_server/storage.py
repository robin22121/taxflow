"""파일 저장 (로컬 ./storage/)."""

from __future__ import annotations

import hashlib
from pathlib import Path

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"
STORAGE_DIR.mkdir(exist_ok=True)


def save(file_id: str, ext: str, data: bytes) -> tuple[str, str]:
    """파일 저장 후 (상대 경로, sha256) 반환."""
    filename = f"{file_id}{ext}"
    path = STORAGE_DIR / filename
    path.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    return f"./storage/{filename}", sha


def load(filename: str) -> bytes:
    path = STORAGE_DIR / Path(filename).name
    return path.read_bytes()


def path_of(filename: str) -> Path:
    return STORAGE_DIR / Path(filename).name
