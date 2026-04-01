from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
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
    created_at: datetime

    model_config = {"from_attributes": False}


class ImageListResponse(BaseModel):
    items: list[ImageOut]


class ImageFacetsOut(BaseModel):
    """Distinct metadata values in the library (for dynamic filter controls)."""

    garment_types: list[str]
    styles: list[str]
    occasions: list[str]
    color_palettes: list[str]


class ImageUpdateBody(BaseModel):
    description: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    annotations: Optional[dict[str, Any]] = None


class AnnotationsPatchBody(BaseModel):
    """Designer annotations. Omitted fields are left unchanged."""

    tags: Optional[list[str]] = None
    notes: Optional[str] = None


def _public_file_url(request: Request, file_path: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/{file_path.lstrip('/')}"


def _to_out(request: Request, row: Image) -> ImageOut:
    return ImageOut(
        id=row.id,
        file_path=row.file_path,
        url=_public_file_url(request, row.file_path),
        description=row.description,
        metadata=row.meta,
        annotations=row.annotations,
        created_at=row.created_at,
    )


@router.get("", response_model=ImageListResponse)
def list_images(
    request: Request,
    session: Session = Depends(get_session),
    garment_type: Optional[str] = None,
    style: Optional[str] = None,
    occasion: Optional[str] = None,
    color: Optional[str] = None,
    color_palette: Optional[str] = None,
    q: Optional[str] = None,
    search: Optional[str] = None,
):
    """
    List images. Metadata filters: case-insensitive substring on JSON fields.
    ``q`` / ``search`` matches **description**, annotation **notes**, and any **tag**
    (substring). ``color`` is shorthand for ``color_palette``.
    """
    palette: Optional[str] = None
    if color_palette not in (None, ""):
        palette = color_palette
    elif color not in (None, ""):
        palette = color

    desc: Optional[str] = None
    if q not in (None, ""):
        desc = q
    elif search not in (None, ""):
        desc = search
    rows = image_filters.query_images(
        session,
        garment_type=garment_type,
        style=style,
        occasion=occasion,
        color_palette=palette,
        description_query=desc,
    )
    return ImageListResponse(items=[_to_out(request, r) for r in rows])


@router.post("/upload", response_model=ImageOut)
async def upload_image(
    request: Request,
    session: Session = Depends(get_session),
    file: UploadFile = File(...),
):
    try:
        rel_path, abs_path = await image_service.save_upload_to_disk(file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        classification = classify_image(abs_path)
    except Exception as e:
        abs_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=502,
            detail=f"Image classification failed: {e}",
        ) from e

    meta = classification_metadata(classification)
    row = image_crud.create_image(
        session,
        file_path=rel_path,
        description=classification.description,
        metadata=meta,
        annotations=normalize_annotations({}),
    )
    return _to_out(request, row)


@router.get("/facets", response_model=ImageFacetsOut)
def image_facets(session: Session = Depends(get_session)):
    data = image_filters.get_image_facets(session)
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
    if body.tags is None and body.notes is None:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: tags, notes",
        )
    row = image_crud.get_image(session, image_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Image not found")
    merged = merge_annotation_patch(row.annotations, tags=body.tags, notes=body.notes)
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
