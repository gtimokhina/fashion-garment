"""OpenAI text embeddings for semantic search over image descriptions."""

from __future__ import annotations

import math
import os
from typing import Sequence

from openai import OpenAI

from services import config as _env  # noqa: F401 — load .env


def _client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to app/backend/.env for semantic search."
        )
    return OpenAI(api_key=api_key.strip())


def embedding_model() -> str:
    return os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip() or "text-embedding-3-small"


def embed_text(text: str) -> list[float]:
    """Single text → embedding vector (L2-normalized for stable cosine similarity)."""
    t = (text or "").strip()
    if not t:
        raise ValueError("Cannot embed empty text")
    client = _client()
    r = client.embeddings.create(model=embedding_model(), input=t)
    vec = list(r.data[0].embedding)
    return _l2_normalize(vec)


def _l2_normalize(vec: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec))
    if n == 0:
        return vec
    return [x / n for x in vec]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Dot product of L2-normalized vectors equals cosine similarity."""
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))
