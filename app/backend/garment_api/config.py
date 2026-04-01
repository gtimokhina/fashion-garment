from __future__ import annotations

import os
from pathlib import Path


def get_database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./data/app.db")


def get_cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS")
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def sqlite_connect_args(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def database_path_from_url(url: str) -> Path | None:
    """If SQLite file URL, return path so parent dirs can be created."""
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    raw = url.removeprefix(prefix).lstrip("./")
    return Path(__file__).resolve().parent.parent / raw
