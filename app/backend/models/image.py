from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ImageRecord(SQLModel, table=True):
    """Stored garment inspiration image metadata."""

    __tablename__ = "image_record"

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str = Field(index=True)
    created_at: datetime = Field(default_factory=_utc_now)
