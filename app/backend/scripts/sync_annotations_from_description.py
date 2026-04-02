#!/usr/bin/env python3
"""
Populate designer tags and notes from each row's AI description + structured metadata.

Calls the same OpenAI model as classification to suggest **3–5** tags and **one short
sentence** of notes (compact; no “The image features…” openings). By default replaces
existing annotations; use --merge to union tags and append notes.

  cd app/backend && source .venv/bin/activate
  python3 scripts/sync_annotations_from_description.py --dry-run
  python3 scripts/sync_annotations_from_description.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from sqlalchemy import select  # noqa: E402

from models.database import SessionLocal  # noqa: E402
from models.image import Image  # noqa: E402
from services.annotation_from_description import suggest_annotations_from_description  # noqa: E402
from services.annotation_utils import merge_annotation_patch, normalize_annotations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync tags/notes from stored AI description + metadata (OpenAI).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without calling OpenAI or writing the DB",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of images to process",
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge with existing tags (dedupe union) and append new notes to existing notes",
    )
    parser.add_argument(
        "--skip-empty",
        action="store_true",
        help="Skip rows with empty description",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        rows = list(session.scalars(select(Image).order_by(Image.id.asc())).all())
    finally:
        session.close()

    if args.limit is not None:
        rows = rows[: args.limit]

    if not rows:
        print("No images in database.")
        return 0

    ok = 0
    failed = 0
    skipped = 0

    for row in rows:
        if args.skip_empty and not (row.description or "").strip():
            skipped += 1
            continue
        if args.dry_run:
            print(f"[dry-run] id={row.id} would sync annotations from description ({len(row.description)} chars)")
            ok += 1
            continue

        session = SessionLocal()
        try:
            fresh = session.get(Image, row.id)
            if fresh is None:
                continue
            suggested = suggest_annotations_from_description(
                fresh.description,
                fresh.meta,
            )
            if args.merge:
                existing = normalize_annotations(fresh.annotations)
                merged_tags = list(dict.fromkeys([*existing["tags"], *suggested["tags"]]))
                notes_a = existing["notes"].strip()
                notes_b = suggested["notes"].strip()
                if notes_a and notes_b:
                    notes = f"{notes_a}\n\n{notes_b}"
                else:
                    notes = notes_a or notes_b
                merged = merge_annotation_patch(
                    fresh.annotations,
                    tags=merged_tags,
                    notes=notes,
                )
                fresh.annotations = merged
            else:
                fresh.annotations = suggested
            session.commit()
            print(f"id={row.id}: tags={len(suggested['tags'])} notes={len(suggested['notes'])} chars")
            ok += 1
        except Exception as e:
            session.rollback()
            print(f"id={row.id}: FAILED {e}", file=sys.stderr)
            failed += 1
        finally:
            session.close()

    print(f"Done. updated={ok} failed={failed} skipped={skipped} dry_run={args.dry_run}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
