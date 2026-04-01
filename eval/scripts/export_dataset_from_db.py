#!/usr/bin/env python3
"""
Export images and structured labels from the SQLite ``image`` table into
``eval/data/example_dataset/`` for use with ``eval/run_eval.py``.

Copies each file from ``app/backend/uploads/…`` into ``images/`` and writes
``labels.json`` with garment_type, style, occasion, and color (from ``color_palette``)
taken from the stored ``metadata`` JSON — i.e. the same gold labels the classifier
produced when the row was created (or last updated).

Usage (backend venv recommended):

  cd app/backend && source .venv/bin/activate
  python3 ../../eval/scripts/export_dataset_from_db.py

Options: --dataset path, --limit N, --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "app" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.chdir(BACKEND_ROOT)

from sqlalchemy import select  # noqa: E402

from models.database import SessionLocal  # noqa: E402
from models.image import Image  # noqa: E402


def _safe_filename(image_id: int, file_path: str) -> str:
    base = Path(file_path).name
    if not base or base == ".":
        base = f"image_{image_id}.jpg"
    stem = Path(base).stem
    suffix = Path(base).suffix.lower() or ".jpg"
    stem_clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", stem)[:80]
    return f"db_{image_id}_{stem_clean}{suffix}"


def _meta_str(meta: dict, key: str) -> str:
    v = meta.get(key) if isinstance(meta, dict) else None
    if v is None:
        return ""
    return str(v).strip()


def labels_from_row(meta: dict) -> dict[str, str]:
    return {
        "garment_type": _meta_str(meta, "garment_type"),
        "style": _meta_str(meta, "style"),
        "occasion": _meta_str(meta, "occasion"),
        "color": _meta_str(meta, "color_palette"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export DB images + metadata to eval dataset folder.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=REPO_ROOT / "eval" / "data" / "example_dataset",
        help="Target dataset directory (default: eval/data/example_dataset)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max rows to export")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions only; do not copy files or write labels.json",
    )
    args = parser.parse_args()

    dataset_dir = args.dataset.resolve()
    images_dir = dataset_dir / "images"

    session = SessionLocal()
    try:
        rows = list(session.scalars(select(Image).order_by(Image.id.asc())).all())
    finally:
        session.close()

    if args.limit is not None:
        rows = rows[: args.limit]

    if not rows:
        print("No images in database.", file=sys.stderr)
        return 1

    items: list[dict] = []
    missing = 0

    for row in rows:
        src = (BACKEND_ROOT / row.file_path).resolve()
        dest_name = _safe_filename(row.id, row.file_path)
        rel_image = f"images/{dest_name}"
        meta = row.meta if isinstance(row.meta, dict) else {}
        labels = labels_from_row(meta)

        if not args.dry_run:
            if not src.is_file():
                print(f"Skip id={row.id}: file not found {src}", file=sys.stderr)
                missing += 1
                continue
            images_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, images_dir / dest_name)

        items.append({"image": rel_image, "labels": labels})

    payload = {"version": 1, "items": items}

    if args.dry_run:
        print(json.dumps(payload, indent=2))
        print(f"[dry-run] would write {len(items)} item(s) to {dataset_dir / 'labels.json'}")
        return 0

    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "labels.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"Wrote {len(items)} item(s) to {dataset_dir / 'labels.json'} "
        f"(skipped missing files: {missing})"
    )
    return 0 if missing == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
