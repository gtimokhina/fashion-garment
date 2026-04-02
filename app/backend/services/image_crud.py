"""CRUD operations for Image ORM."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.image import Image


def create_image(
    session: Session,
    *,
    file_path: str,
    description: str,
    metadata: dict[str, Any],
    annotations: dict[str, Any] | None = None,
    ai_raw_response: str | None = None,
) -> Image:
    row = Image(
        file_path=file_path,
        description=description,
        meta=metadata,
        annotations=annotations if annotations is not None else {},
        ai_raw_response=ai_raw_response,
    )
    session.add(row)
    session.flush()
    try:
        from services.image_embedding import refresh_description_embedding

        refresh_description_embedding(session, row)
    except Exception:
        row.description_embedding = None
    session.commit()
    session.refresh(row)
    return row


def get_image(session: Session, image_id: int) -> Image | None:
    return session.get(Image, image_id)


def list_images(session: Session, *, limit: int | None = None) -> list[Image]:
    stmt = select(Image).order_by(Image.created_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).all())


def update_image(
    session: Session,
    image_id: int,
    *,
    file_path: str | None = None,
    description: str | None = None,
    metadata: dict[str, Any] | None = None,
    annotations: dict[str, Any] | None = None,
) -> Image | None:
    row = session.get(Image, image_id)
    if row is None:
        return None
    if file_path is not None:
        row.file_path = file_path
    if description is not None:
        row.description = description
    if metadata is not None:
        row.meta = metadata
    if annotations is not None:
        row.annotations = annotations
    if description is not None:
        try:
            from services.image_embedding import refresh_description_embedding

            refresh_description_embedding(session, row)
        except Exception:
            row.description_embedding = None
    session.commit()
    session.refresh(row)
    return row


def delete_image(session: Session, image_id: int) -> bool:
    row = session.get(Image, image_id)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True
