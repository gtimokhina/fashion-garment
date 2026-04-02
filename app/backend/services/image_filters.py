"""Filter / facet queries for Image rows (SQLite + JSON metadata)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

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

# Metadata JSON keys accepted for substring filters (``value`` or legacy string).
META_FILTER_KEYS: tuple[str, ...] = (
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
)

# API response keys for GET /facets → meta JSON key (refined faceting per dimension).
_META_FACET_KEYS: dict[str, str] = {
    "garment_types": "garment_type",
    "styles": "style",
    "materials": "material",
    "color_palettes": "color_palette",
    "patterns": "pattern",
    "seasons": "season",
    "occasions": "occasion",
    "consumer_profiles": "consumer_profile",
    "trend_notes": "trend_notes",
    "location_contexts": "location_context",
}


def _escape_like(pattern: str) -> str:
    return pattern.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _meta_value_like_expr(key: str):
    """Coalesce ``$.key.value`` (new shape) with ``$.key`` (legacy plain string)."""
    return func.coalesce(
        cast(func.json_extract(Image.meta, f"$.{key}.value"), String),
        cast(func.json_extract(Image.meta, f"$.{key}"), String),
        "",
    )


def _json_substring_match_key(key: str, needle: str):
    if not needle or not needle.strip():
        return None
    inner = _escape_like(needle.strip().lower())
    blob = func.lower(_meta_value_like_expr(key))
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
    meta_filters: dict[str, str] | None = None,
    description_query: str | None = None,
) -> list[Image]:
    """
    Filter images by substring match on structured metadata (case-insensitive).
    ``meta_filters`` keys must be in ``META_FILTER_KEYS``; unknown keys are ignored.
    """
    stmt = select(Image).order_by(Image.created_at.desc())
    clauses: list = []
    mf = {k: v for k, v in (meta_filters or {}).items() if k in META_FILTER_KEYS and v and str(v).strip()}
    for key, needle in mf.items():
        c = _json_substring_match_key(key, needle)
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
    meta_filters: dict[str, str] | None = None,
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
    candidates = query_images(session, meta_filters=meta_filters, description_query=None)
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
        rows = query_images(session, meta_filters=meta_filters, description_query=q_raw)
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
    meta_filters: dict[str, str] | None = None,
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
    candidates = query_images(session, meta_filters=meta_filters, description_query=None)
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
        rows = query_images(session, meta_filters=meta_filters, description_query=q_raw)
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
        rows = query_images(session, meta_filters=meta_filters, description_query=q_raw)
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


def _facet_filters_excluding(
    active: dict[str, str | None],
    exclude_meta_key: str,
) -> dict[str, str]:
    """Build meta_filters for queries, omitting one dimension for refined faceting."""
    out: dict[str, str] = {}
    for k in META_FILTER_KEYS:
        if k == exclude_meta_key:
            continue
        v = active.get(k)
        if v is not None and str(v).strip():
            out[k] = str(v).strip()
    return out


def get_image_facets(
    session: Session,
    *,
    active_filters: dict[str, str | None] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Faceted value counts for filter UI.

    For each facet dimension, counts exclude that dimension's filter but apply all
    other facet filters (refined faceting). Uses the same substring semantics as
    ``query_images``.     ``metadata`` values are read via ``meta_field_value`` (legacy
    strings or ``value``+``confidence`` objects).
    """
    from services.metadata_fields import meta_field_value

    active: dict[str, str | None] = {k: v for k, v in (active_filters or {}).items()}

    out: dict[str, list[dict[str, Any]]] = {}
    for facet_key, meta_key in _META_FACET_KEYS.items():
        mf = _facet_filters_excluding(active, meta_key)
        rows = query_images(session, meta_filters=mf, description_query=None)
        counts: Counter[str] = Counter()

        for row in rows:
            meta = row.meta
            if not isinstance(meta, dict):
                continue
            v = meta_field_value(meta.get(meta_key))
            if v:
                counts[v] += 1

        items = [{"value": k, "count": counts[k]} for k in sorted(counts.keys(), key=str.lower)]
        out[facet_key] = items
    return out


def _z(v: str | None) -> str | None:
    if v is None or not str(v).strip():
        return None
    return str(v).strip()


def build_active_filters_dict(
    *,
    garment_type: str | None = None,
    style: str | None = None,
    material: str | None = None,
    color: str | None = None,
    color_palette: str | None = None,
    pattern: str | None = None,
    season: str | None = None,
    occasion: str | None = None,
    consumer_profile: str | None = None,
    trend_notes: str | None = None,
    location_context: str | None = None,
) -> dict[str, str | None]:
    """All meta filter dimensions for faceting (None = no filter). ``color`` aliases ``color_palette``."""
    palette = color_palette
    if palette in (None, "") and color not in (None, ""):
        palette = color
    return {
        "garment_type": _z(garment_type),
        "style": _z(style),
        "material": _z(material),
        "color_palette": _z(palette),
        "pattern": _z(pattern),
        "season": _z(season),
        "occasion": _z(occasion),
        "consumer_profile": _z(consumer_profile),
        "trend_notes": _z(trend_notes),
        "location_context": _z(location_context),
    }


def build_meta_filters(
    *,
    garment_type: str | None = None,
    style: str | None = None,
    material: str | None = None,
    color: str | None = None,
    color_palette: str | None = None,
    pattern: str | None = None,
    season: str | None = None,
    occasion: str | None = None,
    consumer_profile: str | None = None,
    trend_notes: str | None = None,
    location_context: str | None = None,
) -> dict[str, str]:
    """Collect non-empty query params into a ``meta_filters`` dict for ``query_images``."""
    af = build_active_filters_dict(
        garment_type=garment_type,
        style=style,
        material=material,
        color=color,
        color_palette=color_palette,
        pattern=pattern,
        season=season,
        occasion=occasion,
        consumer_profile=consumer_profile,
        trend_notes=trend_notes,
        location_context=location_context,
    )
    return {k: v for k, v in af.items() if v is not None}
