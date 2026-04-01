from __future__ import annotations

from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from garment_api.config import database_path_from_url, get_database_url, sqlite_connect_args

_database_url = get_database_url()
_db_path = database_path_from_url(_database_url)
if _db_path is not None:
    _db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    _database_url,
    connect_args=sqlite_connect_args(_database_url),
)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
