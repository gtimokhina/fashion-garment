"""
OpenAI GPT-4o vision classification for garment / fashion inspiration images.

``OPENAI_API_KEY`` and optional ``OPENAI_MODEL`` are read from the process
environment. Values can be set in ``app/backend/.env`` (loaded automatically
via ``services.config``).
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path

from openai import OpenAI

from services import config as _env  # noqa: F401 — loads .env from BACKEND_ROOT before OpenAI reads os.environ
from pydantic import BaseModel, Field, ValidationError

# Keys the model must return (plus description).
_STRUCTURE_KEYS = (
    "garment_type",
    "style",
    "material",
    "color_palette",
    "pattern",
    "season",
    "occasion",
    "consumer_profile",
    "trend_notes",
    "location_context",
)

_JSON_SCHEMA_HINT = (
    "Return a single JSON object with exactly these string fields (use empty string if truly unknown): "
    '"description" (2–4 sentences, natural language), '
    + ", ".join(f'"{k}"' for k in _STRUCTURE_KEYS)
    + ". Do not use null; use empty strings. No markdown, no code fences, no text outside the JSON object."
)

_SYSTEM_PROMPT = (
    "You are an expert fashion and retail vision analyst. "
    "You describe garment and scene context for designers. "
    "You must output only valid JSON matching the user's schema. "
    "Be specific and professional; infer conservatively when uncertain."
)

_USER_PROMPT = f"""Analyze this fashion or street-style inspiration image.

{_JSON_SCHEMA_HINT}

Field guidance:
- garment_type: primary item (e.g. trench coat, midi skirt).
- style: aesthetic (e.g. minimalist, streetwear, heritage).
- material: visible or likely fabrics (e.g. wool twill, denim).
- color_palette: main colors and neutrals, comma-separated.
- pattern: e.g. solid, stripe, floral, or "none".
- season: likely wear season(s).
- occasion: e.g. casual, work, evening, athletic.
- consumer_profile: likely target demographic in short phrase.
- trend_notes: short note on trends or timelessness.
- location_context: setting (e.g. urban street, studio, market) and region hint if visible.
"""


class ImageClassification(BaseModel):
    """Structured output from classify_image."""

    description: str = Field(..., description="Natural-language description of the image.")
    garment_type: str = ""
    style: str = ""
    material: str = ""
    color_palette: str = ""
    pattern: str = ""
    season: str = ""
    occasion: str = ""
    consumer_profile: str = ""
    trend_notes: str = ""
    location_context: str = ""


def classification_metadata(obj: ImageClassification) -> dict[str, str]:
    """Structured attribute dict for persistence (excludes ``description``)."""
    return {key: getattr(obj, key) for key in _STRUCTURE_KEYS}


def _get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to the environment or app/backend/.env (do not commit secrets)."
        )
    return OpenAI(api_key=api_key.strip())


def _model_name() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o").strip() or "gpt-4o"


def _image_data_url(path: Path) -> tuple[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {path}")
    mime, _ = mimetypes.guess_type(str(path))
    if not mime or not mime.startswith("image/"):
        mime = "image/jpeg"
    data = path.read_bytes()
    b64 = base64.standard_b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}", mime


def _strip_json_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _parse_classification(raw: str) -> ImageClassification:
    cleaned = _strip_json_fences(raw)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return ImageClassification.model_validate(data)


def _vision_completion(client: OpenAI, image_path: Path) -> str:
    data_url, _ = _image_data_url(image_path)
    response = client.chat.completions.create(
        model=_model_name(),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _USER_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url, "detail": "high"},
                    },
                ],
            },
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Empty completion from OpenAI")
    return content


def _repair_completion(client: OpenAI, broken_text: str, error_hint: str) -> str:
    repair_prompt = f"""The following text was supposed to be a single JSON object with keys:
"description", {", ".join(repr(k) for k in _STRUCTURE_KEYS)}.
All values must be JSON strings.

Parsing failed: {error_hint}

Broken output:
{broken_text}

Output only the corrected JSON object. No markdown or explanation."""

    response = client.chat.completions.create(
        model=_model_name(),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": repair_prompt},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Empty completion from OpenAI (repair pass)")
    return content


def classify_image(image_path: str | Path, *, max_retries: int = 3) -> ImageClassification:
    """
    Classify a local image with GPT-4o (vision).

    Reads OPENAI_API_KEY from the environment. Optional: OPENAI_MODEL (default gpt-4o).

    On JSON parse or validation failure, retries with a text-only repair call (same model,
    no second image upload) up to ``max_retries`` times total (first call is vision, later
    calls attempt to fix the previous raw string).
    """
    path = Path(image_path).expanduser().resolve()
    if max_retries < 1:
        raise ValueError("max_retries must be at least 1")

    client = _get_client()
    last_raw = ""
    last_error = ""

    for attempt in range(max_retries):
        if attempt == 0:
            last_raw = _vision_completion(client, path)
        else:
            last_raw = _repair_completion(client, last_raw, last_error)

        try:
            return _parse_classification(last_raw)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_error = f"{type(e).__name__}: {e}"
            if attempt == max_retries - 1:
                raise ValueError(
                    f"Failed to obtain valid classification after {max_retries} attempt(s). "
                    f"Last error: {last_error}"
                ) from e
