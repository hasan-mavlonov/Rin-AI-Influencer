# core/database.py
from sqlmodel import SQLModel, create_engine, Session
from core.config import Config
from core.logger import get_logger

log = get_logger("DB")

engine = create_engine(Config.DB_URL, echo=False)

def init_db():
    from models import PostDraft, PostHistory  # import models lazily
    SQLModel.metadata.create_all(engine)
    log.info(f"Database initialized at {Config.DB_URL}")

def get_session() -> Session:
    return Session(engine)

if __name__ == "__main__":
    init_db()
