"""E2E: multipart upload (classify mocked) then filter via GET /api/images."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.ai_classifier import (
    AttributeField,
    ClassificationResult,
    ImageClassification,
)


def _stub_classify_result() -> ClassificationResult:
    classification = ImageClassification(
        description="Structured blazer outfit for work.",
        garment_type=AttributeField(value="blazer", confidence=0.91),
        style=AttributeField(value="business casual", confidence=0.82),
        material=AttributeField(value="wool", confidence=0.75),
        color_palette=AttributeField(value="navy, white", confidence=0.88),
        pattern=AttributeField(value="solid", confidence=0.9),
        season=AttributeField(value="fall", confidence=0.5),
        occasion=AttributeField(value="work", confidence=0.85),
        consumer_profile=AttributeField(value="", confidence=0.1),
        trend_notes=AttributeField(value="", confidence=0.1),
        location_context=AttributeField(value="studio", confidence=0.4),
        location_continent=AttributeField(value="", confidence=0.0),
        location_country=AttributeField(value="", confidence=0.0),
        location_city=AttributeField(value="", confidence=0.0),
        time_year=AttributeField(value="", confidence=0.0),
        time_month=AttributeField(value="", confidence=0.0),
        designer=AttributeField(value="", confidence=0.0),
    )
    raw = (
        '{"description":"Structured blazer outfit for work.",'
        '"garment_type":{"value":"blazer","confidence":0.91}}'
    )
    return ClassificationResult(classification=classification, raw_json=raw)


# Minimal valid PNG (1×1)
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_upload_then_filter_by_garment_type(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import routes.images as images_routes

    monkeypatch.setattr(
        images_routes,
        "classify_image",
        lambda path: _stub_classify_result(),
    )

    files = {"files": ("e2e.png", _TINY_PNG, "image/png")}
    up = client.post("/api/images/upload", files=files)
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["errors"] == []
    assert len(body["items"]) == 1
    assert "blazer" in body["items"][0]["metadata"]["garment_type"]["value"].lower()

    listed = client.get("/api/images", params={"garment_type": "blazer"})
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == body["items"][0]["id"]

    # Description search (q) hits stored description
    q = client.get("/api/images", params={"q": "Structured blazer"})
    assert q.status_code == 200
    assert len(q.json()["items"]) == 1
