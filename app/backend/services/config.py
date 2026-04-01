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


def _env_float(key: str, default: str, *, clamp: tuple[float, float]) -> float:
    """Read float from env; strip inline ``#`` comments; defaults match ``.env.example``."""
    raw = os.getenv(key, default)
    if raw is None:
        raw = default
    raw = raw.split("#", 1)[0].strip()
    try:
        v = float(raw)
    except ValueError:
        v = float(default.split("#", 1)[0].strip())
    lo, hi = clamp
    return max(lo, min(hi, v))


def semantic_search_min_score() -> float:
    """Minimum cosine similarity (0–1) to keep a row in semantic search results."""
    return _env_float("SEMANTIC_SEARCH_MIN_SCORE", "0.28", clamp=(0.0, 1.0))


def semantic_search_relative_to_best() -> float:
    """Also require score >= this fraction of the best match (reduces long-tail junk)."""
    return _env_float("SEMANTIC_SEARCH_RELATIVE_TO_BEST", "0.88", clamp=(0.5, 1.0))
