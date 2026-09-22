from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import Base, IdMixin, TimestampMixin


class MessageLog(Base, IdMixin, TimestampMixin):
    """수집 세션과 무관한 발송 기록 (신고안내 등 — plan/13-messaging-activation.md §5.3)."""

    __tablename__ = "message_logs"
    __table_args__ = (Index("ix_message_logs_office_created", "tax_office_id", "created_at"),)

    tax_office_id: Mapped[str] = mapped_column(ForeignKey("tax_offices.id"))
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"))
    sent_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    purpose: Mapped[str] = mapped_column(String(40))  # FILING_NOTICE
    tax_type: Mapped[str | None] = mapped_column(String(20))  # WITHHOLDING | VAT | INCOME | CORPORATE
    requested_channel: Mapped[str] = mapped_column(String(20))  # sms | alimtalk
    channel: Mapped[str] = mapped_column(String(40))  # 실제 최종 채널 (sms_aligo, alimtalk_aligo ...)
    to_phone: Mapped[str | None] = mapped_column(String(40))
    body: Mapped[str] = mapped_column(Text)
    template_code: Mapped[str | None] = mapped_column(String(40))
    accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_msg_id: Mapped[str | None] = mapped_column(String(100))
    error: Mapped[str | None] = mapped_column(String(500))
