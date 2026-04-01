import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_ROOT / ".env")


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


def database_path_from_url(url: str) -> Optional[Path]:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    raw = url.removeprefix(prefix).lstrip("./")
    return BACKEND_ROOT / raw


def upload_dir_path() -> Path:
    return BACKEND_ROOT / "uploads"


def semantic_search_min_score() -> float:
    """Minimum cosine similarity (0–1) to keep a row in semantic search results."""
    raw = os.getenv("SEMANTIC_SEARCH_MIN_SCORE", "0.28")
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return 0.28


def semantic_search_relative_to_best() -> float:
    """Also require score >= this fraction of the best match (reduces long-tail junk)."""
    raw = os.getenv("SEMANTIC_SEARCH_RELATIVE_TO_BEST", "0.88")
    try:
        return max(0.5, min(1.0, float(raw)))
    except ValueError:
        return 0.88
