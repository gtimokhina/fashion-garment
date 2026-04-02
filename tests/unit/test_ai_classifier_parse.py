"""Unit tests: parsing model JSON into ImageClassification (no OpenAI or DB)."""

from __future__ import annotations

import json

import pytest

from services.ai_classifier import (
    AttributeField,
    ImageClassification,
    _parse_classification,
    _parse_classification_with_raw,
    _strip_json_fences,
)


def test_strip_json_fences_markdown() -> None:
    raw = """```json
{"description": "Test.", "garment_type": {"value": "coat", "confidence": 0.9}}
```"""
    cleaned = _strip_json_fences(raw)
    data = json.loads(cleaned)
    assert data["description"] == "Test."
    assert data["garment_type"]["value"] == "coat"


def test_parse_classification_minimal_json_roundtrip() -> None:
    raw = json.dumps(
        {
            "description": "A red wool coat on a city street.",
            "garment_type": {"value": "coat", "confidence": 0.92},
            "style": {"value": "minimalist", "confidence": 0.7},
            "occasion": {"value": "casual", "confidence": 0.65},
            "color_palette": {"value": "red, charcoal, beige", "confidence": 0.88},
            "material": {"value": "wool", "confidence": 0.8},
            "pattern": {"value": "solid", "confidence": 0.9},
            "season": {"value": "fall", "confidence": 0.5},
            "consumer_profile": {"value": "", "confidence": 0.1},
            "trend_notes": {"value": "", "confidence": 0.1},
            "location_context": {"value": "urban", "confidence": 0.6},
            "location_continent": {"value": "", "confidence": 0.0},
            "location_country": {"value": "", "confidence": 0.0},
            "location_city": {"value": "", "confidence": 0.0},
            "time_year": {"value": "", "confidence": 0.0},
            "time_month": {"value": "", "confidence": 0.0},
            "designer": {"value": "", "confidence": 0.0},
        }
    )
    obj = _parse_classification(raw)
    assert isinstance(obj, ImageClassification)
    assert obj.description.startswith("A red wool")
    assert obj.garment_type.value == "coat"
    assert obj.garment_type.confidence == pytest.approx(0.92)
    assert obj.color_palette.value == "red, charcoal, beige"

    obj2, normalized = _parse_classification_with_raw(raw)
    assert obj2.garment_type.value == "coat"
    assert "coat" in normalized


def test_parse_classification_string_attribute_coerced() -> None:
    """Legacy or partial shapes: plain string for an attribute coerces via AttributeField validator."""
    raw = json.dumps(
        {
            "description": "Desc.",
            "garment_type": "blazer",
            "style": {"value": "preppy", "confidence": 0.5},
            "material": {"value": "", "confidence": 0.0},
            "color_palette": {"value": "navy", "confidence": 0.9},
            "pattern": {"value": "", "confidence": 0.0},
            "season": {"value": "", "confidence": 0.0},
            "occasion": {"value": "work", "confidence": 0.6},
            "consumer_profile": {"value": "", "confidence": 0.0},
            "trend_notes": {"value": "", "confidence": 0.0},
            "location_context": {"value": "", "confidence": 0.0},
            "location_continent": {"value": "", "confidence": 0.0},
            "location_country": {"value": "", "confidence": 0.0},
            "location_city": {"value": "", "confidence": 0.0},
            "time_year": {"value": "", "confidence": 0.0},
            "time_month": {"value": "", "confidence": 0.0},
            "designer": {"value": "", "confidence": 0.0},
        }
    )
    obj = _parse_classification(raw)
    assert obj.garment_type.value == "blazer"


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        _parse_classification("not json {}")


def test_parse_missing_description_raises() -> None:
    with pytest.raises(Exception):
        _parse_classification(json.dumps({"garment_type": {"value": "x", "confidence": 1}}))


def test_attribute_field_bounds() -> None:
    af = AttributeField(value="test", confidence=0.5)
    assert af.value == "test"
    af2 = AttributeField.model_validate({"value": "z", "confidence": 2.0})
    assert af2.confidence == 1.0
