"""Persist description embeddings on Image rows."""

from __future__ import annotations

from sqlalchemy.orm import Session

from models.image import Image
from services import embeddings as emb


def refresh_description_embedding(session: Session, row: Image) -> None:
    """Compute embedding from ``row.description`` and save (commits inside caller)."""
    text = (row.description or "").strip()
    if not text:
        row.description_embedding = None
        return
    row.description_embedding = emb.embed_text(text)
