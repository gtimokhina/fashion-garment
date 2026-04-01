"""Filter / facet queries for Image rows (SQLite + JSON metadata)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import String, and_, cast, func, or_, select, text
from sqlalchemy.orm import Session

from models.image import Image
from services.config import semantic_search_min_score, semantic_search_relative_to_best

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
    """Semantic search: filtered rows with parallel cosine scores (same order)."""

    items: list[Image]
    scores: list[float]
    used_keyword_fallback: bool = False


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
