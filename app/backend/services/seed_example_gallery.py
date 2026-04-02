"""Seed one demo row + file when the image table is empty (first clone / fresh volume).

Set env ``FASHION_GARMENT_SKIP_SEED=1`` to disable (used by pytest and optional for operators).
Bundled file: ``app/backend/seed_assets/example-inspiration.png`` (AI-generated demo asset).
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from sqlalchemy import func, select

from models.database import SessionLocal
from models.image import Image
from services import image_crud
from services.config import BACKEND_ROOT, upload_dir_path

SEED_REL_DIR = Path("seed_assets")
SEED_FILENAME = "example-inspiration.png"


def _seed_metadata() -> dict:
    return {
        "garment_type": {"value": "overcoat", "confidence": 0.88},
        "style": {"value": "minimalist", "confidence": 0.82},
        "material": {"value": "wool", "confidence": 0.85},
        "color_palette": {"value": "camel, beige", "confidence": 0.9},
        "pattern": {"value": "solid", "confidence": 0.92},
        "season": {"value": "fall", "confidence": 0.65},
        "occasion": {"value": "work", "confidence": 0.7},
        "consumer_profile": {"value": "contemporary professional", "confidence": 0.55},
        "trend_notes": {"value": "elevated basics", "confidence": 0.5},
        "location_context": {"value": "studio", "confidence": 0.8},
        "location_continent": {"value": "", "confidence": 0.0},
        "location_country": {"value": "", "confidence": 0.0},
        "location_city": {"value": "", "confidence": 0.0},
        "time_year": {"value": "", "confidence": 0.0},
        "time_month": {"value": "", "confidence": 0.0},
        "designer": {"value": "", "confidence": 0.0},
    }


def seed_example_if_empty() -> None:
    raw_skip = (os.getenv("FASHION_GARMENT_SKIP_SEED") or "").strip().lower()
    if raw_skip in ("1", "true", "yes", "on"):
        return

    source = BACKEND_ROOT / SEED_REL_DIR / SEED_FILENAME
    if not source.is_file():
        return

    with SessionLocal() as session:
        n = session.scalar(select(func.count()).select_from(Image))
        if n:
            return

    upload_dir_path().mkdir(parents=True, exist_ok=True)
    ext = source.suffix.lower() or ".png"
    dest_name = f"{uuid.uuid4().hex}{ext}"
    rel_path = f"uploads/{dest_name}"
    dest_abs = upload_dir_path() / dest_name
    shutil.copy2(source, dest_abs)

    description = (
        "Camel wool overcoat on a hanger against a warm beige studio wall "
        "with soft natural light—minimal lookbook styling."
    )
    annotations = {
        "tags": ["example", "demo"],
        "notes": "Shipped as a sample row so the gallery is not empty on first run.",
        "designer": "",
    }
    ai_raw = (
        '{"description":"' + description.replace('"', '\\"') + '",'
        '"garment_type":{"value":"overcoat","confidence":0.88}}'
    )

    try:
        with SessionLocal() as session:
            n = session.scalar(select(func.count()).select_from(Image))
            if n:
                dest_abs.unlink(missing_ok=True)
                return

            image_crud.create_image(
                session,
                file_path=rel_path,
                description=description,
                metadata=_seed_metadata(),
                annotations=annotations,
                ai_raw_response=ai_raw.strip(),
            )
    except Exception:
        dest_abs.unlink(missing_ok=True)
        raise
