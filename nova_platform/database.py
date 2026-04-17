import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from nova_platform.models import Base

DATA_DIR = Path.home() / ".nova-platform"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "nova.db"

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()
