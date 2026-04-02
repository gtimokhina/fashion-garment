"""
OpenAI GPT-4o vision classification for garment / fashion inspiration images.

``OPENAI_API_KEY`` and optional ``OPENAI_MODEL`` are read from the process
environment. Values can be set in the repo root ``.env`` (loaded automatically via ``services.config``).

Structured attributes are stored as ``{"value": str, "confidence": float}`` per field.
If the model omits ``confidence``, :func:`services.metadata_fields.heuristic_confidence_for_value`
is applied after parsing (see that module).
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from services import config as _env  # noqa: F401 — loads .env from BACKEND_ROOT before OpenAI reads os.environ
from services.metadata_fields import heuristic_confidence_for_value

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
    "location_continent",
    "location_country",
    "location_city",
    "time_year",
    "time_month",
    "designer",
)

_ATTR_SCHEMA = (
    'Each of these must be a JSON object: {"value": "<text>", "confidence": <number 0 to 1>} '
    "where confidence is your estimated certainty that the value is correct for this image. "
    "Use empty string and low confidence (e.g. 0.1–0.3) when uncertain."
)

_JSON_SCHEMA_HINT = (
    'Return a single JSON object with a string field "description" (2–4 sentences, natural language) '
    f"and these fields: {', '.join(repr(k) for k in _STRUCTURE_KEYS)}. "
    f"{_ATTR_SCHEMA} "
    "Do not use null for value; use empty strings. Confidence must be a number. "
    "No markdown, no code fences, no text outside the JSON object."
)

_SYSTEM_PROMPT = (
    "You are an expert fashion and retail vision analyst. "
    "You describe garment and scene context for designers. "
    "You must output only valid JSON matching the user's schema. "
    "For each structured attribute, provide both value and confidence (0–1). "
    "Be specific and professional; infer conservatively when uncertain."
)

_USER_PROMPT = f"""Analyze this fashion or street-style inspiration image.

{_JSON_SCHEMA_HINT}

Field guidance (for ``value``; set ``confidence`` accordingly):
- garment_type: primary item (e.g. trench coat, midi skirt).
- style: aesthetic (e.g. minimalist, streetwear, heritage).
- material: visible or likely fabrics (e.g. wool twill, denim).
- color_palette: main colors and neutrals, comma-separated.
- pattern: e.g. solid, stripe, floral, or "none".
- season: likely wear season(s).
- occasion: e.g. casual, work, evening, athletic.
- consumer_profile: likely target demographic in short phrase.
- trend_notes: short note on trends or timelessness.
- location_context: free-form scene (e.g. urban street, studio, runway).
- location_continent: continent if inferable from architecture, signage, or context; else empty.
- location_country: country or region (e.g. Japan, France) if inferable; else empty.
- location_city: city name if inferable; else empty.
- time_year: calendar year if inferable from visible text, fashion context, or scene; else empty.
- time_month: month name or number if inferable; else empty.
- designer: visible brand, designer name, or logo text if readable in the image; else empty.
"""


class AttributeField(BaseModel):
    """Single structured attribute with model- or heuristic-derived confidence."""

    model_config = ConfigDict(extra="ignore")

    value: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="before")
    @classmethod
    def coerce_legacy_or_partial(cls, data: Any) -> Any:
        if data is None:
            return {"value": "", "confidence": 0.0}
        if isinstance(data, str):
            v = data.strip()
            return {"value": v, "confidence": heuristic_confidence_for_value(v)}
        if isinstance(data, dict):
            raw_v = data.get("value", "")
            v = raw_v if isinstance(raw_v, str) else (str(raw_v) if raw_v is not None else "")
            v = v.strip()
            c = data.get("confidence")
            if c is None:
                conf = heuristic_confidence_for_value(v)
            else:
                try:
                    conf = max(0.0, min(1.0, float(c)))
                except (TypeError, ValueError):
                    conf = heuristic_confidence_for_value(v)
            return {"value": v, "confidence": conf}
        return {"value": "", "confidence": 0.0}


class ImageClassification(BaseModel):
    """Structured output from classify_image."""

    description: str = Field(..., description="Natural-language description of the image.")
    garment_type: AttributeField = Field(default_factory=AttributeField)
    style: AttributeField = Field(default_factory=AttributeField)
    material: AttributeField = Field(default_factory=AttributeField)
    color_palette: AttributeField = Field(default_factory=AttributeField)
    pattern: AttributeField = Field(default_factory=AttributeField)
    season: AttributeField = Field(default_factory=AttributeField)
    occasion: AttributeField = Field(default_factory=AttributeField)
    consumer_profile: AttributeField = Field(default_factory=AttributeField)
    trend_notes: AttributeField = Field(default_factory=AttributeField)
    location_context: AttributeField = Field(default_factory=AttributeField)
    location_continent: AttributeField = Field(default_factory=AttributeField)
    location_country: AttributeField = Field(default_factory=AttributeField)
    location_city: AttributeField = Field(default_factory=AttributeField)
    time_year: AttributeField = Field(default_factory=AttributeField)
    time_month: AttributeField = Field(default_factory=AttributeField)
    designer: AttributeField = Field(default_factory=AttributeField)


@dataclass(frozen=True)
class ClassificationResult:
    """Parsed classification plus the JSON text that was successfully parsed (fences stripped)."""

    classification: ImageClassification
    raw_json: str


def classification_metadata(obj: ImageClassification) -> dict[str, Any]:
    """Structured attribute dict for persistence (excludes ``description``): value + confidence each."""
    out: dict[str, Any] = {}
    for key in _STRUCTURE_KEYS:
        af = getattr(obj, key)
        if isinstance(af, AttributeField):
            out[key] = {
                "value": af.value,
                "confidence": round(float(af.confidence), 4),
            }
        else:
            v = str(af) if af is not None else ""
            out[key] = {
                "value": v.strip(),
                "confidence": round(heuristic_confidence_for_value(v), 4),
            }
    return out


def _get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to the environment or the repo root .env (do not commit secrets)."
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
    return _parse_classification_with_raw(raw)[0]


def _parse_classification_with_raw(raw: str) -> tuple[ImageClassification, str]:
    cleaned = _strip_json_fences(raw)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return ImageClassification.model_validate(data), cleaned


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
"description" (string), and for each of: {", ".join(repr(k) for k in _STRUCTURE_KEYS)},
an object {{"value": string, "confidence": number between 0 and 1}}.

{_ATTR_SCHEMA}

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


def classify_image(image_path: str | Path, *, max_retries: int = 3) -> ClassificationResult:
    """
    Classify a local image with GPT-4o (vision).

    Reads OPENAI_API_KEY from the environment. Optional: OPENAI_MODEL (default gpt-4o).

    On JSON parse or validation failure, retries with a text-only repair call (same model,
    no second image upload) up to ``max_retries`` times total (first call is vision, later
    calls attempt to fix the previous raw string).

    Returns :class:`ClassificationResult` with the parsed model and ``raw_json`` (normalized
    JSON text after stripping markdown fences) that was successfully parsed.
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
            classification, cleaned = _parse_classification_with_raw(last_raw)
            return ClassificationResult(classification=classification, raw_json=cleaned)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_error = f"{type(e).__name__}: {e}"
            if attempt == max_retries - 1:
                raise ValueError(
                    f"Failed to obtain valid classification after {max_retries} attempt(s). "
                    f"Last error: {last_error}"
                ) from e
