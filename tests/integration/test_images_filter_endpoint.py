"""Integration tests: GET /api/images metadata filtering (real DB + FastAPI stack)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient
from models.database import SessionLocal
from models.image import Image


def _meta(garment: str, style: str = "streetwear") -> dict:
    return {
        "garment_type": {"value": garment, "confidence": 0.9},
        "style": {"value": style, "confidence": 0.8},
        "material": {"value": "cotton", "confidence": 0.7},
        "color_palette": {"value": "black", "confidence": 0.85},
        "pattern": {"value": "solid", "confidence": 0.9},
        "season": {"value": "", "confidence": 0.1},
        "occasion": {"value": "casual", "confidence": 0.7},
        "consumer_profile": {"value": "", "confidence": 0.1},
        "trend_notes": {"value": "", "confidence": 0.1},
        "location_context": {"value": "", "confidence": 0.1},
        "location_continent": {"value": "", "confidence": 0.0},
        "location_country": {"value": "", "confidence": 0.0},
        "location_city": {"value": "", "confidence": 0.0},
        "time_year": {"value": "", "confidence": 0.0},
        "time_month": {"value": "", "confidence": 0.0},
        "designer": {"value": "", "confidence": 0.0},
    }


def test_list_images_filters_by_garment_type_substring(client: TestClient) -> None:
    with SessionLocal() as s:
        s.add(
            Image(
                file_path="uploads/one.jpg",
                description="First.",
                meta=_meta("trench coat"),
                annotations={"tags": [], "notes": "", "designer": ""},
                created_at=datetime.now(timezone.utc),
            )
        )
        s.add(
            Image(
                file_path="uploads/two.jpg",
                description="Second.",
                meta=_meta("sneakers"),
                annotations={"tags": [], "notes": "", "designer": ""},
                created_at=datetime.now(timezone.utc),
            )
        )
        s.commit()

    r = client.get("/api/images", params={"garment_type": "trench"})
    assert r.status_code == 200
    data = r.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["description"] == "First."
    meta = data["items"][0]["metadata"]
    assert "trench" in meta["garment_type"]["value"].lower()


def test_list_images_filters_by_style_and_occasion(client: TestClient) -> None:
    with SessionLocal() as s:
        s.add(
            Image(
                file_path="uploads/a.jpg",
                description="A",
                meta=_meta("blazer", style="minimalist"),
                annotations={"tags": [], "notes": "", "designer": ""},
                created_at=datetime.now(timezone.utc),
            )
        )
        s.commit()

    r = client.get(
        "/api/images",
        params={"style": "minimalist", "occasion": "casual"},
    )
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1


def test_list_images_no_match_returns_empty(client: TestClient) -> None:
    with SessionLocal() as s:
        s.add(
            Image(
                file_path="uploads/x.jpg",
                description="X",
                meta=_meta("hat"),
                annotations={"tags": [], "notes": "", "designer": ""},
                created_at=datetime.now(timezone.utc),
            )
        )
        s.commit()

    r = client.get("/api/images", params={"garment_type": "nonexistent_xyz"})
    assert r.status_code == 200
    assert r.json()["items"] == []
