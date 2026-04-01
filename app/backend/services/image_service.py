from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile

from services.config import upload_dir_path

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# Relative path prefix under BACKEND_ROOT (matches StaticFiles mount).
UPLOAD_SUBDIR = "uploads"


def ensure_upload_dir() -> Path:
    p = upload_dir_path()
    p.mkdir(parents=True, exist_ok=True)
    return p


async def save_upload_to_disk(file: UploadFile) -> tuple[str, Path]:
    """
    Save upload under uploads/. Returns (file_path relative to BACKEND_ROOT, absolute path).
    """
    if not file.filename:
        raise ValueError("Missing filename")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file type")

    ensure_upload_dir()
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    abs_path = upload_dir_path() / stored_name
    content = await file.read()
    abs_path.write_bytes(content)

    rel = f"{UPLOAD_SUBDIR}/{stored_name}"
    return rel, abs_path.resolve()
