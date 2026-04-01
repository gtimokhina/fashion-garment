from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlmodel import Session, select

from models.image import ImageRecord
from services.config import upload_dir_path

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def list_images(session: Session) -> list[ImageRecord]:
    stmt = select(ImageRecord).order_by(ImageRecord.created_at.desc())
    return list(session.exec(stmt).all())


async def save_upload(session: Session, file: UploadFile) -> ImageRecord:
    if not file.filename:
        raise ValueError("Missing filename")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported file type")

    stored_name = f"{uuid.uuid4().hex}{suffix}"
    dest = upload_dir_path() / stored_name

    content = await file.read()
    dest.write_bytes(content)

    record = ImageRecord(filename=stored_name)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record
