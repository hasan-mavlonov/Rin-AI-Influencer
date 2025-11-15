# core/database.py
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.exc import SQLAlchemyError

from core.config import Config
from core.logger import get_logger

log = get_logger("DB")

try:
    engine = create_engine(Config.DB_URL, echo=False)
except SQLAlchemyError as exc:
    log.error(f"Failed to initialize database engine: {exc}")
    engine = None


def init_db():
    from models import PostDraft, PostHistory  # import models lazily
    if engine is None:
        log.error("Database engine unavailable; cannot initialize tables.")
        return

    try:
        SQLModel.metadata.create_all(engine)
        log.info(f"Database initialized at {Config.DB_URL}")
    except SQLAlchemyError as exc:
        log.error(f"Failed to create database tables: {exc}")


def get_session() -> Session:
    if engine is None:
        raise RuntimeError("Database engine is not available; session cannot be created.")

    try:
        return Session(engine)
    except SQLAlchemyError as exc:
        log.error(f"Failed to open database session: {exc}")
        raise


if __name__ == "__main__":
    init_db()
