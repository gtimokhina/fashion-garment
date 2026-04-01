#!/usr/bin/env python3
"""
Reset designer annotations (tags + notes) for every image row to empty.

Designer annotations are stored separately from AI description/metadata and are
intended for real, image-specific notes — use this after bulk imports with
placeholder tags/notes.

  cd app/backend && python3 scripts/clear_all_annotations.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from sqlalchemy import select  # noqa: E402

from models.database import SessionLocal  # noqa: E402
from models.image import Image  # noqa: E402
from services.annotation_utils import normalize_annotations  # noqa: E402

EMPTY = normalize_annotations({})


def main() -> int:
    session = SessionLocal()
    try:
        rows = list(session.scalars(select(Image)).all())
        for row in rows:
            row.annotations = EMPTY
        session.commit()
        print(f"Cleared designer annotations on {len(rows)} image(s).")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
