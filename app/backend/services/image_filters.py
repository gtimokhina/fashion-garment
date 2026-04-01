"""Filter / facet queries for Image rows (SQLite + JSON metadata)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import String, and_, cast, func, or_, select, text
from sqlalchemy.orm import Session

from models.image import Image
from services.config import (
    hybrid_min_combined_score,
    semantic_search_min_score,
    semantic_search_relative_to_best,
)

# Hybrid search weights (fixed 50/50; see ``query_images_hybrid`` docstring).
_HYBRID_W_KEYWORD = 0.5
_HYBRID_W_EMBEDDING = 0.5

# json_extract paths for AI metadata (column `metadata` in DB, `meta` on model).
_JSON_PATHS = {
    "garment_type": "$.garment_type",
    "style": "$.style",
    "occasion": "$.occasion",
    "color_palette": "$.color_palette",
}

_FACET_KEYS = {
    "garment_types": "$.garment_type",
    "styles": "$.style",
    "occasions": "$.occasion",
    "color_palettes": "$.color_palette",
}


def _escape_like(pattern: str) -> str:
    return pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _json_substring_match(column_path: str, needle: str):
    if not needle or not needle.strip():
        return None
    inner = _escape_like(needle.strip().lower())
    blob = func.lower(
        cast(func.coalesce(func.json_extract(Image.meta, column_path), ""), String)
    )
    return blob.like(f"%{inner}%", escape="\\")


def _keyword_match_substring(row: Image, raw_needle: str) -> bool:
    """
    Same intent as the SQL ``LIKE`` / ``instr`` branch in ``query_images``:
    case-insensitive substring in description, annotation notes, or any tag.
    """
    if not raw_needle or not str(raw_needle).strip():
        return False
    low = raw_needle.strip().lower()
    if low in (row.description or "").lower():
        return True
    ann = row.annotations if isinstance(row.annotations, dict) else {}
    notes = ann.get("notes")
    if isinstance(notes, str) and low in notes.lower():
        return True
    tags = ann.get("tags")
    if isinstance(tags, list):
        for t in tags:
            if isinstance(t, str) and low in t.lower():
                return True
    return False


def _keyword_score(row: Image, raw_needle: str) -> float:
    """Binary keyword relevance: 1.0 if any text field matches, else 0.0 (see hybrid docstring)."""
    return 1.0 if _keyword_match_substring(row, raw_needle) else 0.0


def query_images(
    session: Session,
    *,
    garment_type: str | None = None,
    style: str | None = None,
    occasion: str | None = None,
    color_palette: str | None = None,
    description_query: str | None = None,
) -> list[Image]:
    stmt = select(Image).order_by(Image.created_at.desc())
    clauses: list = []

    c = _json_substring_match(_JSON_PATHS["garment_type"], garment_type or "")
    if c is not None:
        clauses.append(c)
    c = _json_substring_match(_JSON_PATHS["style"], style or "")
    if c is not None:
        clauses.append(c)
    c = _json_substring_match(_JSON_PATHS["occasion"], occasion or "")
    if c is not None:
        clauses.append(c)
    c = _json_substring_match(_JSON_PATHS["color_palette"], color_palette or "")
    if c is not None:
        clauses.append(c)

    if description_query and description_query.strip():
        raw_needle = description_query.strip().lower()
        t = _escape_like(raw_needle)
        pattern = f"%{t}%"
        desc_clause = func.lower(Image.description).like(pattern, escape="\\")
        notes_clause = func.lower(
            cast(
                func.coalesce(func.json_extract(Image.annotations, "$.notes"), ""),
                String,
            )
        ).like(pattern, escape="\\")
        # Tags: substring match without LIKE (avoids ESCAPE issues in raw SQL).
        tags_clause = text(
            "EXISTS (SELECT 1 FROM json_each("
            "COALESCE(json_extract(image.annotations, '$.tags'), json_array())"
            ") AS j WHERE typeof(j.value) = 'text' "
            "AND instr(lower(j.value), :ann_sub) > 0)"
        ).bindparams(ann_sub=raw_needle)
        clauses.append(or_(desc_clause, notes_clause, tags_clause))

    if clauses:
        stmt = stmt.where(and_(*clauses))
    return list(session.scalars(stmt).all())


@dataclass
class SemanticSearchResult:
    """Embedding-only search: cosine scores parallel to ``items`` (see ``query_images_semantic``)."""

    items: list[Image]
    scores: list[float]
    used_keyword_fallback: bool = False


@dataclass
class HybridSearchResult:
    """Hybrid search: parallel score lists aligned with ``items`` (see ``query_images_hybrid``)."""

    items: list[Image]
    embedding_scores: list[float]
    keyword_scores: list[float]
    combined_scores: list[float]
    used_keyword_fallback: bool = False


def query_images_hybrid(
    session: Session,
    *,
    garment_type: str | None = None,
    style: str | None = None,
    occasion: str | None = None,
    color_palette: str | None = None,
    search_query: str | None = None,
) -> HybridSearchResult:
    """
    **Hybrid ranking** over facet-filtered candidates (no SQL text filter on ``q``).

    For each row we compute:

    - **keyword_score** ∈ {0, 1}: ``1`` if the query appears as a case-insensitive substring
      in the **description**, annotation **notes**, or any **tag** — mirroring the keyword
      branch of ``query_images`` (SQL ``LIKE`` / ``instr`` semantics), else ``0``.

    - **embedding_sim** ∈ [0, 1]: cosine similarity between the query text embedding and the
      stored ``description_embedding`` (L2-normalized vectors). ``0`` if there is no embedding.

    - **combined_score** = ``0.5 * keyword_score + 0.5 * embedding_sim`` — equal weight to
      lexical overlap and semantic similarity so explicit keyword hits are boosted while
      paraphrases / synonyms can still rank via embeddings.

    Rows are sorted by ``combined_score`` descending. Rows with ``combined_score`` below
    ``HYBRID_MIN_COMBINED_SCORE`` are dropped. If none remain, we fall back to pure SQL
    keyword filtering (same facets + substring ``q``) and return that list with scores zeroed.
    """
    from services import embeddings as emb

    q_raw = (search_query or "").strip()
    candidates = query_images(
        session,
        garment_type=garment_type,
        style=style,
        occasion=occasion,
        color_palette=color_palette,
        description_query=None,
    )
    if not q_raw:
        z = [0.0] * len(candidates)
        return HybridSearchResult(
            items=candidates,
            embedding_scores=z,
            keyword_scores=z,
            combined_scores=z,
            used_keyword_fallback=False,
        )

    q_emb = emb.embed_text(q_raw)
    min_combined = hybrid_min_combined_score()

    scored: list[tuple[Image, float, float, float]] = []
    for row in candidates:
        kw = _keyword_score(row, q_raw)
        emb_sim = 0.0
        vec = row.description_embedding
        if vec and isinstance(vec, list):
            try:
                emb_sim = emb.cosine_similarity(q_emb, [float(x) for x in vec])
            except (TypeError, ValueError):
                emb_sim = 0.0
        combined = _HYBRID_W_KEYWORD * kw + _HYBRID_W_EMBEDDING * emb_sim
        scored.append((row, emb_sim, kw, combined))

    scored.sort(key=lambda x: -x[3])
    kept = [t for t in scored if t[3] >= min_combined]

    if not kept:
        rows = query_images(
            session,
            garment_type=garment_type,
            style=style,
            occasion=occasion,
            color_palette=color_palette,
            description_query=q_raw,
        )
        z = [0.0] * len(rows)
        return HybridSearchResult(
            items=rows,
            embedding_scores=z,
            keyword_scores=z,
            combined_scores=z,
            used_keyword_fallback=True,
        )

    return HybridSearchResult(
        items=[t[0] for t in kept],
        embedding_scores=[t[1] for t in kept],
        keyword_scores=[t[2] for t in kept],
        combined_scores=[t[3] for t in kept],
        used_keyword_fallback=False,
    )


def query_images_semantic(
    session: Session,
    *,
    garment_type: str | None = None,
    style: str | None = None,
    occasion: str | None = None,
    color_palette: str | None = None,
    search_query: str | None = None,
) -> SemanticSearchResult:
    """
    Same facet filters as ``query_images`` (no substring ``q``). When ``search_query``
    is non-empty, score each row by cosine similarity vs the query embedding, then
    **drop** matches below a minimum score and below a fraction of the best score.
    If nothing survives, fall back to keyword search (same facets + ``search_query``).
    Rows without ``description_embedding`` are excluded from semantic results.
    """
    from services import embeddings as emb

    q_raw = (search_query or "").strip()
    candidates = query_images(
        session,
        garment_type=garment_type,
        style=style,
        occasion=occasion,
        color_palette=color_palette,
        description_query=None,
    )
    if not q_raw:
        return SemanticSearchResult(items=candidates, scores=[0.0] * len(candidates))

    q_emb = emb.embed_text(q_raw)
    min_abs = semantic_search_min_score()
    rel = semantic_search_relative_to_best()

    scored: list[tuple[float, Image]] = []
    for row in candidates:
        vec = row.description_embedding
        if not vec or not isinstance(vec, list):
            continue
        try:
            s = emb.cosine_similarity(q_emb, [float(x) for x in vec])
        except (TypeError, ValueError):
            continue
        scored.append((s, row))

    if not scored:
        rows = query_images(
            session,
            garment_type=garment_type,
            style=style,
            occasion=occasion,
            color_palette=color_palette,
            description_query=q_raw,
        )
        return SemanticSearchResult(
            items=rows,
            scores=[0.0] * len(rows),
            used_keyword_fallback=True,
        )

    scored.sort(key=lambda x: -x[0])
    best = scored[0][0]
    threshold = max(min_abs, best * rel)
    kept = [(s, r) for s, r in scored if s >= threshold]

    if not kept:
        rows = query_images(
            session,
            garment_type=garment_type,
            style=style,
            occasion=occasion,
            color_palette=color_palette,
            description_query=q_raw,
        )
        return SemanticSearchResult(
            items=rows,
            scores=[0.0] * len(rows),
            used_keyword_fallback=True,
        )

    return SemanticSearchResult(
        items=[r for _, r in kept],
        scores=[s for s, _ in kept],
        used_keyword_fallback=False,
    )


def get_image_facets(session: Session) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for facet_key, path in _FACET_KEYS.items():
        stmt = select(func.json_extract(Image.meta, path)).distinct()
        vals = session.scalars(stmt).all()
        cleaned = sorted(
            {(str(v) or "").strip() for v in vals if v is not None and str(v).strip()},
            key=str.lower,
        )
        out[facet_key] = cleaned
    return out
