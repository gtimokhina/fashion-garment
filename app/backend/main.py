from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from models.database import init_db
from routes.health import router as health_router
from routes.images import router as images_router
from services.config import get_cors_origins, upload_dir_path
from services.seed_example_gallery import seed_example_if_empty


@asynccontextmanager
async def lifespan(_app: FastAPI):
    upload_dir_path().mkdir(parents=True, exist_ok=True)
    init_db()
    seed_example_if_empty()
    yield


app = FastAPI(
    title="Fashion Garment API",
    description="Inspiration imagery: uploads, metadata, search, annotations.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(images_router, prefix="/api")

_upload_dir = upload_dir_path()
_upload_dir.mkdir(parents=True, exist_ok=True)
app.mount(
    "/uploads",
    StaticFiles(directory=str(_upload_dir)),
    name="uploads",
)
