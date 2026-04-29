from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.client import Client
from app.models.collection import CollectionSession


class SecureToken(Base, IdMixin, TimestampMixin):
    """주민번호·입사일 등 민감정보 일회성 입력 토큰."""

    __tablename__ = "secure_tokens"
    __table_args__ = (Index("ix_secure_tokens_token", "token", unique=True),)

    token: Mapped[str] = mapped_column(String(64))
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    collection_session_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_sessions.id")
    )
    purpose: Mapped[str] = mapped_column(String(40))  # NEW_HIRE_RRN / FOLLOWUP / etc
    context: Mapped[dict | None] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(Boolean, default=False)

    client: Mapped[Client] = relationship()
    collection_session: Mapped[CollectionSession | None] = relationship()
