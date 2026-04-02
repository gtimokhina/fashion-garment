from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models.database import get_session
from models.image import Image
from services import image_service
from services.ai_classifier import classification_metadata, classify_image
from services.config import BACKEND_ROOT
from services import image_crud
from services import image_filters
from services.annotation_utils import merge_annotation_patch, normalize_annotations

router = APIRouter(prefix="/images", tags=["images"])


class ImageOut(BaseModel):
    id: int
    file_path: str
    url: str
    description: str
    metadata: dict[str, Any] = Field(description="AI structured attributes")
    annotations: dict[str, Any]
    ai_raw_response: Optional[str] = Field(
        default=None,
        description="Raw JSON text from the model (normalized) when available; null for older rows.",
    )
    created_at: datetime
    semantic_score: Optional[float] = Field(
        default=None,
        description="Embedding cosine similarity (0–1) when semantic/hybrid search is used.",
    )
    keyword_score: Optional[float] = Field(
        default=None,
        description="Lexical match score 0 or 1 when hybrid search is used.",
    )
    combined_score: Optional[float] = Field(
        default=None,
        description="Hybrid ranking score 0–1 when hybrid search is used (0.5×keyword + 0.5×embedding).",
    )

    model_config = {"from_attributes": False}


class ImageListResponse(BaseModel):
    items: list[ImageOut]
    semantic_mode: Optional[bool] = Field(
        default=None,
        description="True when the request used semantic=true with a non-empty query.",
    )
    hybrid_mode: Optional[bool] = Field(
        default=None,
        description="True when hybrid (keyword + embedding) ranking was used.",
    )
    keyword_fallback: Optional[bool] = Field(
        default=None,
        description="True when search fell back to SQL substring matching (embedding-only or hybrid).",
    )


class UploadErrorOut(BaseModel):
    filename: str
    detail: str


class ImageBatchUploadResponse(BaseModel):
    """Result of uploading one or more images (each classified and saved independently)."""

    items: list[ImageOut]
    errors: list[UploadErrorOut]


class FacetValueOut(BaseModel):
    """Single facet value with image count (refined by other active facet filters)."""

    value: str
    count: int


class ImageFacetsOut(BaseModel):
    """Facet values with counts for dynamic filter controls (see ``GET /images/facets``)."""

    garment_types: list[FacetValueOut]
    styles: list[FacetValueOut]
    materials: list[FacetValueOut]
    color_palettes: list[FacetValueOut]
    patterns: list[FacetValueOut]
    seasons: list[FacetValueOut]
    occasions: list[FacetValueOut]
    consumer_profiles: list[FacetValueOut]
    trend_notes: list[FacetValueOut]
    location_contexts: list[FacetValueOut]


class ImageUpdateBody(BaseModel):
    description: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    annotations: Optional[dict[str, Any]] = None


class AnnotationsPatchBody(BaseModel):
    """Designer annotations. Omitted fields are left unchanged."""

    tags: Optional[list[str]] = None
    notes: Optional[str] = None
    designer: Optional[str] = None


def _public_file_url(request: Request, file_path: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/{file_path.lstrip('/')}"


def _to_out(
    request: Request,
    row: Image,
    *,
    semantic_score: Optional[float] = None,
    keyword_score: Optional[float] = None,
    combined_score: Optional[float] = None,
) -> ImageOut:
    return ImageOut(
        id=row.id,
        file_path=row.file_path,
        url=_public_file_url(request, row.file_path),
        description=row.description,
        metadata=row.meta,
        annotations=row.annotations,
        ai_raw_response=row.ai_raw_response,
        created_at=row.created_at,
        semantic_score=semantic_score,
        keyword_score=keyword_score,
        combined_score=combined_score,
    )


async def _ingest_one_upload(
    request: Request,
    session: Session,
    file: UploadFile,
) -> tuple[ImageOut | None, str | None]:
    """Save, classify, persist one upload. Returns (result, error_detail)."""
    label = file.filename or "unnamed"
    try:
        rel_path, abs_path = await image_service.save_upload_to_disk(file)
    except ValueError as e:
        return None, str(e)
    try:
        classification_result = classify_image(abs_path)
    except Exception as e:
        abs_path.unlink(missing_ok=True)
        return None, f"Image classification failed: {e}"

    classification = classification_result.classification
    meta = classification_metadata(classification)
    row = image_crud.create_image(
        session,
        file_path=rel_path,
        description=classification.description,
        metadata=meta,
        annotations=normalize_annotations({}),
        ai_raw_response=classification_result.raw_json,
    )
    return _to_out(request, row), None


@router.get("", response_model=ImageListResponse)
def list_images(
    request: Request,
    session: Session = Depends(get_session),
    garment_type: Optional[str] = None,
    style: Optional[str] = None,
    material: Optional[str] = None,
    color: Optional[str] = None,
    color_palette: Optional[str] = None,
    pattern: Optional[str] = None,
    season: Optional[str] = None,
    occasion: Optional[str] = None,
    consumer_profile: Optional[str] = None,
    trend_notes: Optional[str] = None,
    location_context: Optional[str] = None,
    q: Optional[str] = None,
    search: Optional[str] = None,
    semantic: bool = Query(
        False,
        description="When true with non-empty q/search, use embedding-based ranking (and hybrid by default).",
    ),
    hybrid: bool = Query(
        True,
        description="With semantic=true: combine keyword (LIKE-style) and embedding scores; false = embedding-only.",
    ),
):
    """
    List images. Metadata filters: case-insensitive substring on JSON fields (see
    ``META_FILTER_KEYS`` in ``image_filters``). ``q`` / ``search`` matches **description**,
    annotation **notes**, and any **tag** (substring). ``color`` is shorthand for ``color_palette``.
    With ``semantic=true`` and non-empty ``q``: default **hybrid** ranking
    ``combined_score = 0.5 * keyword_score + 0.5 * embedding_similarity`` (see each item).
    Set ``hybrid=false`` for embedding-only thresholding (legacy). ``keyword_fallback``
    if the API falls back to SQL substring-only results.
    """
    meta_filters = image_filters.build_meta_filters(
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

    desc: Optional[str] = None
    if q not in (None, ""):
        desc = q
    elif search not in (None, ""):
        desc = search

    if semantic and desc and str(desc).strip():
        if hybrid:
            result = image_filters.query_images_hybrid(
                session,
                meta_filters=meta_filters,
                search_query=desc,
            )
            items_out = [
                _to_out(
                    request,
                    r,
                    semantic_score=e,
                    keyword_score=k,
                    combined_score=c,
                )
                for r, e, k, c in zip(
                    result.items,
                    result.embedding_scores,
                    result.keyword_scores,
                    result.combined_scores,
                )
            ]
            return ImageListResponse(
                items=items_out,
                semantic_mode=True,
                hybrid_mode=True,
                keyword_fallback=result.used_keyword_fallback,
            )

        result = image_filters.query_images_semantic(
            session,
            meta_filters=meta_filters,
            search_query=desc,
        )
        items_out = [
            _to_out(request, r, semantic_score=s)
            for r, s in zip(result.items, result.scores)
        ]
        return ImageListResponse(
            items=items_out,
            semantic_mode=True,
            hybrid_mode=False,
            keyword_fallback=result.used_keyword_fallback,
        )

    rows = image_filters.query_images(
        session,
        meta_filters=meta_filters,
        description_query=desc,
    )
    return ImageListResponse(items=[_to_out(request, r) for r in rows])


@router.post("/upload", response_model=ImageBatchUploadResponse)
async def upload_images(
    request: Request,
    session: Session = Depends(get_session),
    files: list[UploadFile] = File(..., description="One or more images (same field name: files)"),
):
    if not files:
        raise HTTPException(status_code=400, detail="Send at least one file under form field 'files'")

    items: list[ImageOut] = []
    errors: list[UploadErrorOut] = []

    for f in files:
        out, err = await _ingest_one_upload(request, session, f)
        if out is not None:
            items.append(out)
        else:
            errors.append(
                UploadErrorOut(filename=f.filename or "unnamed", detail=err or "Unknown error")
            )

    return ImageBatchUploadResponse(items=items, errors=errors)


@router.get("/facets", response_model=ImageFacetsOut)
def image_facets(
    session: Session = Depends(get_session),
    garment_type: Optional[str] = None,
    style: Optional[str] = None,
    material: Optional[str] = None,
    color: Optional[str] = None,
    color_palette: Optional[str] = None,
    pattern: Optional[str] = None,
    season: Optional[str] = None,
    occasion: Optional[str] = None,
    consumer_profile: Optional[str] = None,
    trend_notes: Optional[str] = None,
    location_context: Optional[str] = None,
):
    """
    Facet values with counts. Each dimension's counts apply all other facet filters
    but not that dimension (standard faceted search). Omit query params for global
    counts. ``color`` is an alias for ``color_palette``.
    """
    active = image_filters.build_active_filters_dict(
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
    data = image_filters.get_image_facets(session, active_filters=active)
    return ImageFacetsOut(**data)


@router.get("/{image_id}", response_model=ImageOut)
def get_image(image_id: int, request: Request, session: Session = Depends(get_session)):
    row = image_crud.get_image(session, image_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return _to_out(request, row)


@router.patch("/{image_id}/annotations", response_model=ImageOut)
def patch_annotations(
    image_id: int,
    body: AnnotationsPatchBody,
    request: Request,
    session: Session = Depends(get_session),
):
    if body.tags is None and body.notes is None and body.designer is None:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: tags, notes, designer",
        )
    row = image_crud.get_image(session, image_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Image not found")
    merged = merge_annotation_patch(
        row.annotations,
        tags=body.tags,
        notes=body.notes,
        designer=body.designer,
    )
    row = image_crud.update_image(session, image_id, annotations=merged)
    if row is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return _to_out(request, row)


@router.patch("/{image_id}", response_model=ImageOut)
def patch_image(
    image_id: int,
    body: ImageUpdateBody,
    request: Request,
    session: Session = Depends(get_session),
):
    if body.description is None and body.metadata is None and body.annotations is None:
        raise HTTPException(status_code=400, detail="Provide at least one field to update")
    row = image_crud.update_image(
        session,
        image_id,
        description=body.description,
        metadata=body.metadata,
        annotations=body.annotations,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return _to_out(request, row)


@router.delete("/{image_id}", status_code=204)
def remove_image(image_id: int, session: Session = Depends(get_session)):
    row = image_crud.get_image(session, image_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Image not found")
    path = BACKEND_ROOT / row.file_path
    image_crud.delete_image(session, image_id)
    if path.is_file():
        path.unlink()
