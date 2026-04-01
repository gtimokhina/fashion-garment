"""
Derive searchable designer annotations (tags + notes) from the AI description and metadata.

Uses the same OpenAI client/model as classification; output is intended to complement
search with synonyms and alternate phrasing grounded in the stored description.
"""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from services import config as _env  # noqa: F401 — load .env
from services.annotation_utils import normalize_annotations


class SuggestedAnnotations(BaseModel):
    tags: list[str] = Field(default_factory=list, description="Short searchable tags")
    notes: str = Field("", description="Brief note including useful synonyms for discovery")


_SYSTEM = (
    "You help fashion designers build searchable libraries. "
    "You output only valid JSON. Tags must be grounded in the given description and metadata—"
    "include synonyms and alternate terms that someone might search for (e.g. related garment words, "
    "style synonyms, color or mood alternates) without inventing facts not supported by the text."
)

_USER_TEMPLATE = """Given this image record from our library:

**Description (AI-generated):**
{description}

**Structured metadata (may be empty for some fields):**
{meta_lines}

Produce JSON with exactly two keys:
- "tags": array of 5–14 short strings (lowercase, 1–4 words each). Include:
  - key nouns/adjectives from the description rephrased where helpful;
  - synonyms or near-synonyms that appear in or clearly follow from the description;
  - terms from non-empty metadata fields (e.g. garment type, style, occasion) as separate tags when useful.
  No duplicates; no empty strings.
- "notes": one or two short sentences (plain text) that summarize searchable themes and explicitly mention a few synonym pairs or alternatives (e.g. "also searchable as …") so designers see how tags relate to the description. If the description is empty, return empty tags and a short note saying there is no description to derive from.

Return JSON only, no markdown."""


def _get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to app/backend/.env (do not commit secrets)."
        )
    return OpenAI(api_key=api_key.strip())


def _model_name() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o").strip() or "gpt-4o"


def _format_metadata(meta: dict[str, Any] | None) -> str:
    if not meta:
        return "(none)"
    lines: list[str] = []
    for k, v in sorted(meta.items()):
        if v is None or v == "":
            continue
        lines.append(f"- {k}: {v}")
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

    tags = [str(t).strip().lower() for t in parsed.tags if str(t).strip()]
    tags = list(dict.fromkeys(tags))
    notes = parsed.notes.strip() if isinstance(parsed.notes, str) else str(parsed.notes or "").strip()
    return normalize_annotations({"tags": tags, "notes": notes})
