from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return uuid4().hex


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class IdMixin:
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)


__all__ = ["Base", "IdMixin", "TimestampMixin", "_new_id", "_utcnow"]
