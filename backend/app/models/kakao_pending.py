from sqlalchemy import JSON, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import Base, IdMixin, TimestampMixin


class KakaoPendingMessage(Base, IdMixin, TimestampMixin):
    """카카오톡에서 거래처명 없이 전송된 자료의 임시 저장.

    파일/텍스트를 먼저 보내고, 거래처명을 나중에 보내는 2단계 플로우 지원.
    거래처명 수신 후 합쳐서 _ingest_message()에 투입하고 삭제.
    """

    __tablename__ = "kakao_pending_messages"
    __table_args__ = (
        Index("ix_kakao_pending_key", "plusfriend_key"),
    )

    plusfriend_key: Mapped[str] = mapped_column(String(200))
    tax_office_id: Mapped[str] = mapped_column(String(32))
    client_id: Mapped[str | None] = mapped_column(String(32))
    utterance: Mapped[str | None] = mapped_column(Text)
    file_text: Mapped[str | None] = mapped_column(Text)
    attachments_meta: Mapped[dict | None] = mapped_column(JSON)
