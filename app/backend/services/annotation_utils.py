"""Normalize and merge designer annotations JSON ({tags, notes})."""

from __future__ import annotations

from typing import Any, Optional


def normalize_annotations(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not raw:
        return {"tags": [], "notes": ""}
    tags_raw = raw.get("tags")
    if isinstance(tags_raw, list):
        tags = [str(t).strip() for t in tags_raw if str(t).strip()]
    else:
        tags = []
    notes_raw = raw.get("notes", "")
    notes = notes_raw if isinstance(notes_raw, str) else str(notes_raw or "")
    return {"tags": tags, "notes": notes}


def merge_annotation_patch(
    existing: Optional[dict[str, Any]],
    *,
    tags: Optional[list[str]] = None,
    notes: Optional[str] = None,
) -> dict[str, Any]:
    base = normalize_annotations(existing)
    if tags is not None:
        base["tags"] = [str(t).strip() for t in tags if str(t).strip()]
    if notes is not None:
        base["notes"] = notes
    return base
