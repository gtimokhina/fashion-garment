"""
Shared pytest fixtures. DATABASE_URL must be set before importing ``main`` (global SQLAlchemy engine).
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import delete

_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "app" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_fd, _TEST_DB_PATH = tempfile.mkstemp(suffix=".sqlite")
os.close(_fd)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["FASHION_GARMENT_SKIP_SEED"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
from models.database import SessionLocal, init_db  # noqa: E402
from models.image import Image  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _init_db() -> Generator[None, None, None]:
    init_db()
    yield
    try:
        os.unlink(_TEST_DB_PATH)
    except OSError:
        pass


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_image_rows() -> Generator[None, None, None]:
    """Empty the image table before each test for isolation."""
    with SessionLocal() as s:
        s.execute(delete(Image))
        s.commit()
    yield
