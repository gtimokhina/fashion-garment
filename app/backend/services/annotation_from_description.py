"""
Derive searchable designer annotations (tags + notes) from the AI description and metadata.

Uses the same OpenAI client/model as classification; output is intended to complement
search with synonyms and alternate phrasing grounded in the stored description.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from services import config as _env  # noqa: F401 — load .env
from services.annotation_utils import normalize_annotations
from services.metadata_fields import meta_field_value


class SuggestedAnnotations(BaseModel):
    tags: list[str] = Field(default_factory=list, description="Short searchable tags")
    notes: str = Field("", description="Single compact sentence for search context")


_SYSTEM = (
    "You help fashion designers build searchable libraries. "
    "You output only valid JSON. Tags must be grounded in the given description and metadata—"
    "use strong search terms only; do not invent facts not supported by the text."
)

_USER_TEMPLATE = """Given this image record from our library:

**Description (AI-generated):**
{description}

**Structured metadata (may be empty for some fields):**
{meta_lines}

Produce JSON with exactly two keys:
- "tags": array of **3 to 5** short strings only (lowercase, 1–4 words each). Pick the best distinct search terms from the description and non-empty metadata (garment, style, mood, occasion, palette). No duplicates; no empty strings. If the description is empty, use [].
- "notes": **exactly one short sentence** (plain text, max ~25 words). Compact search-oriented summary—e.g. key style + garment + vibe. **Do not** start with "The image features", "The image shows", "This image", or similar filler; start with the substance (e.g. "Minimalist camel coat, muted palette, office-casual."). If there is no description and no metadata, use an empty string for notes.

Return JSON only, no markdown."""

# Strip common model boilerplate at the start of notes.
_BAD_NOTE_OPENERS = (
    "the image features ",
    "the image shows ",
    "the image depicts ",
    "this image features ",
    "this image shows ",
    "this image depicts ",
    "the photo features ",
    "the photo shows ",
)


def _sanitize_notes(notes: str) -> str:
    n = (notes or "").strip()
    if not n:
        return ""
    low = n.lower()
    for prefix in _BAD_NOTE_OPENERS:
        if low.startswith(prefix):
            n = n[len(prefix) :].strip()
            if n and not n[0].isupper():
                n = n[0].upper() + n[1:]
            low = n.lower()
            break
    # First sentence only; keep punctuation.
    parts = re.split(r"(?<=[.!?])\s+", n)
    if parts:
        n = parts[0].strip()
    if len(n) > 280:
        n = n[:277].rstrip() + "…"
    return n


def _cap_tags(tags: list[str], *, hi: int = 5) -> list[str]:
    """At most ``hi`` tags (target 3–5 in the prompt); trim extras."""
    out = [str(t).strip().lower() for t in tags if str(t).strip()]
    out = list(dict.fromkeys(out))
    if len(out) > hi:
        out = out[:hi]
    return out


def _get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to the repo root .env (do not commit secrets)."
        )
    return OpenAI(api_key=api_key.strip())


def _model_name() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o").strip() or "gpt-4o"


def _format_metadata(meta: dict[str, Any] | None) -> str:
    if not meta:
        return "(none)"
    lines: list[str] = []
    for k, v in sorted(meta.items()):
        text = meta_field_value(v)
        if not text:
            continue
        lines.append(f"- {k}: {text}")
    return "\n".join(lines) if lines else "(none)"


def suggest_annotations_from_description(
    description: str,
    metadata: dict[str, Any] | None,
    *,
    client: OpenAI | None = None,
) -> dict[str, Any]:
    """
    Call the chat model to suggest tags and notes from the stored description + metadata.

    Returns a normalized annotations dict ``{"tags": [...], "notes": "..."}``.
    """
    c = client or _get_client()
    meta_lines = _format_metadata(metadata)
    user = _USER_TEMPLATE.format(description=description.strip() or "(empty)", meta_lines=meta_lines)

    response = c.chat.completions.create(
        model=_model_name(),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Empty completion from OpenAI")

    obj = json.loads(content)
    if not isinstance(obj, dict):
        raise ValueError("Expected JSON object")
    try:
        parsed = SuggestedAnnotations.model_validate(obj)
    except ValidationError as e:
        raise ValueError(f"Invalid suggested annotations: {e}") from e

    tags = _cap_tags(parsed.tags, hi=5)
    notes_raw = parsed.notes.strip() if isinstance(parsed.notes, str) else str(parsed.notes or "").strip()
    notes = _sanitize_notes(notes_raw)
    return normalize_annotations({"tags": tags, "notes": notes})
