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


class ImageUpdateBody(BaseModel):
    description: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    annotations: Optional[dict[str, Any]] = None


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
def list_images(request: Request, session: Session = Depends(get_session)):
    rows = image_crud.list_images(session)
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
        annotations={},
    )
    return _to_out(request, row)


@router.get("/{image_id}", response_model=ImageOut)
def get_image(image_id: int, request: Request, session: Session = Depends(get_session)):
    row = image_crud.get_image(session, image_id)
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
