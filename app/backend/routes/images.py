from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlmodel import Session

from models.database import get_session
from services import image_service

router = APIRouter(prefix="/images", tags=["images"])


class ImageOut(BaseModel):
    id: int
    filename: str
    url: str


class ImageListResponse(BaseModel):
    items: list[ImageOut]


def _public_upload_url(request: Request, filename: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/uploads/{filename}"


@router.get("", response_model=ImageListResponse)
def list_images(request: Request, session: Session = Depends(get_session)):
    rows = image_service.list_images(session)
    items = [
        ImageOut(
            id=r.id,
            filename=r.filename,
            url=_public_upload_url(request, r.filename),
        )
        for r in rows
        if r.id is not None
    ]
    return ImageListResponse(items=items)


@router.post("/upload", response_model=ImageOut)
async def upload_image(
    request: Request,
    session: Session = Depends(get_session),
    file: UploadFile = File(...),
):
    try:
        record = await image_service.save_upload(session, file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if record.id is None:
        raise HTTPException(status_code=500, detail="Failed to persist image")
    return ImageOut(
        id=record.id,
        filename=record.filename,
        url=_public_upload_url(request, record.filename),
    )
