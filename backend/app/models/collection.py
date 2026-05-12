import enum
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.client import Client
from app.models.monthly_filing import MonthlyFiling


class CollectionSessionStatus(str, enum.Enum):
    PENDING = "PENDING"  # 알림톡 발송 전
    SENT = "SENT"        # 발송됨, 응답 대기
    RECEIVED = "RECEIVED"  # 응답 수신, 파싱됨
    NEEDS_REVIEW = "NEEDS_REVIEW"  # 검증 필요
    APPROVED = "APPROVED"


class CollectionSession(Base, IdMixin, TimestampMixin):
    """거래처별 자료 수집 세션."""

    __tablename__ = "collection_sessions"
    __table_args__ = (
        Index("ix_collection_filing", "monthly_filing_id"),
        Index("ix_collection_client", "client_id"),
    )

    monthly_filing_id: Mapped[str] = mapped_column(ForeignKey("monthly_filings.id"))
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    status: Mapped[CollectionSessionStatus] = mapped_column(
        Enum(CollectionSessionStatus, native_enum=False, length=20),
        default=CollectionSessionStatus.PENDING,
    )
    request_token: Mapped[str] = mapped_column(String(64))
    request_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    monthly_filing: Mapped[MonthlyFiling] = relationship()
    client: Mapped[Client] = relationship()


class CollectionEvent(Base, IdMixin, TimestampMixin):
    """수집 세션 내 단일 이벤트 (발송/수신/파싱 결과 등)."""

    __tablename__ = "collection_events"
    __table_args__ = (Index("ix_event_session", "session_id"),)

    session_id: Mapped[str] = mapped_column(ForeignKey("collection_sessions.id"))
    event_type: Mapped[str] = mapped_column(String(40))
    # SEND_ALIMTALK / RECEIVE_KAKAO / RECEIVE_EXCEL / RECEIVE_VOICE / PARSE_RESULT / FOLLOWUP_SENT
    channel: Mapped[str | None] = mapped_column(String(40))
    raw_text: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict | None] = mapped_column(JSON)
    file_ref: Mapped[str | None] = mapped_column(String(255))
    sender_name: Mapped[str | None] = mapped_column(String(100))
    received_date: Mapped[date | None] = mapped_column(Date)

    session: Mapped[CollectionSession] = relationship()
