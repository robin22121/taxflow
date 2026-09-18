"""SQLite 엔진·세션. plan/17 §3-9-3."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DB_PATH = Path(__file__).resolve().parent.parent / "db.sqlite"
ENGINE = create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)
SessionLocal = sessionmaker(bind=ENGINE, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_session() -> Session:
    return SessionLocal()


def init_db() -> None:
    from certificate_server import models  # noqa: F401 register models

    Base.metadata.create_all(ENGINE)
