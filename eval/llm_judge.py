"""
Optional LLM-as-judge for eval: semantic agreement between gold labels and classifier output.

Uses the same OpenAI API key as the rest of the backend. Set ``EVAL_JUDGE_MODEL`` to override
the model (defaults to ``OPENAI_MODEL`` or ``gpt-4o``). Text mode is cheaper; vision mode
sends the image again for image-grounded judgments.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

from services import config as _env  # noqa: F401 — load .env


class JudgeResult(BaseModel):
    equivalent: bool = Field(description="True if prediction is semantically acceptable vs gold")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    note: str = Field(default="", description="Brief reason, one short sentence")


_SYSTEM = """You evaluate a single fashion-image metadata field.
The REFERENCE label is treated as ground truth from an annotator.
The PREDICTED label comes from an automated vision classifier.

Decide whether the prediction is semantically consistent with the reference for this field:
- Accept synonyms, normal paraphrases, and reasonable broader/narrower phrasing when they clearly describe the same fact.
- Reject clear mismatches, wrong garment types, wrong occasion, incompatible styles, or missing major colors named in the reference.

Respond with JSON only:
{"equivalent": true or false, "confidence": number from 0 to 1, "note": "one short phrase"}"""


def _client() -> OpenAI:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not set (needed for LLM judge).")
    return OpenAI(api_key=key)


def _judge_model() -> str:
    return (os.environ.get("EVAL_JUDGE_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o").strip()


def _parse_judge_json(raw: str) -> JudgeResult:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Judge output must be a JSON object")
    return JudgeResult.model_validate(data)


def judge_field_text(
    field_name: str,
    gold: str,
    predicted: str,
    image_description: str,
) -> JudgeResult:
    """Judge using gold, prediction, and the classifier's written description (no image)."""
    user = f"""Field: {field_name}

REFERENCE (gold): {gold}
PREDICTED: {predicted}

Classifier image description (context):
{image_description[:4000]}
"""
    client = _client()
    r = client.chat.completions.create(
        model=_judge_model(),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
    )
    content = r.choices[0].message.content or ""
    return _parse_judge_json(content)


def _image_data_url(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    if not mime or not mime.startswith("image/"):
        mime = "image/jpeg"
    b64 = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def judge_field_vision(
    field_name: str,
    gold: str,
    predicted: str,
    image_path: Path,
) -> JudgeResult:
    """Judge with the image visible to the model (second vision call per field)."""
    data_url = _image_data_url(image_path)
    user_text = f"""Field: {field_name}

REFERENCE (gold): {gold}
PREDICTED: {predicted}

Look at the image. Is the PREDICTED value semantically consistent with the REFERENCE for this field?
JSON only: {{"equivalent": bool, "confidence": 0-1, "note": "brief"}}"""

    client = _client()
    r = client.chat.completions.create(
        model=_judge_model(),
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
                ],
            },
        ],
    )
    content = r.choices[0].message.content or ""
    return _parse_judge_json(content)


def safe_judge_text(
    field_name: str,
    gold: str,
    predicted: str,
    description: str,
) -> tuple[JudgeResult | None, str | None]:
    try:
        return judge_field_text(field_name, gold, predicted, description), None
    except (ValidationError, json.JSONDecodeError, ValueError, OSError, RuntimeError) as e:
        return None, str(e)


def safe_judge_vision(
    field_name: str,
    gold: str,
    predicted: str,
    image_path: Path,
) -> tuple[JudgeResult | None, str | None]:
    try:
        return judge_field_vision(field_name, gold, predicted, image_path), None
    except (ValidationError, json.JSONDecodeError, ValueError, OSError, RuntimeError) as e:
        return None, str(e)
