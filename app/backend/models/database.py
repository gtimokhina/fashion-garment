from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from services.config import database_path_from_url, get_database_url, sqlite_connect_args


class Base(DeclarativeBase):
    """SQLAlchemy model base."""


_database_url = get_database_url()
_db_path = database_path_from_url(_database_url)
if _db_path is not None:
    _db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    _database_url,
    connect_args=sqlite_connect_args(_database_url),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    # Import models so metadata is registered before create_all.
    from models.image import Image  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_description_embedding()


def _migrate_sqlite_description_embedding() -> None:
    """Add description_embedding column to existing SQLite DBs (create_all does not alter tables)."""
    if not get_database_url().startswith("sqlite"):
        return
    insp = inspect(engine)
    if "image" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("image")}
    if "description_embedding" in cols:
        return
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE image ADD COLUMN description_embedding JSON"))
        conn.commit()


def get_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
