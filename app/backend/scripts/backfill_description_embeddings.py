#!/usr/bin/env python3
"""Compute and store description_embedding for rows that are missing it."""

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
from services.image_embedding import refresh_description_embedding  # noqa: E402


def main() -> int:
    session = SessionLocal()
    try:
        rows = list(session.scalars(select(Image).order_by(Image.id.asc())).all())
        n = 0
        for row in rows:
            if row.description_embedding is not None:
                continue
            if not (row.description or "").strip():
                continue
            try:
                refresh_description_embedding(session, row)
                session.commit()
                n += 1
                print(f"id={row.id}: ok")
            except Exception as e:
                session.rollback()
                print(f"id={row.id}: skip ({e})", file=sys.stderr)
        print(f"Updated embeddings for {n} row(s).")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
