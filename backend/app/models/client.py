from sqlalchemy import Boolean, ForeignKey, Index, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.tax_office import TaxOffice

# 전용 수신 이메일 도메인 (SendGrid Inbound Parse용)
COLLECT_EMAIL_DOMAIN = "easyonechon.co.kr"


class Client(Base, IdMixin, TimestampMixin):
    """거래처 — 세무사사무소가 담당하는 사업자."""

    __tablename__ = "clients"
    __table_args__ = (
        Index("ix_clients_tax_office", "tax_office_id"),
    )

    tax_office_id: Mapped[str] = mapped_column(ForeignKey("tax_offices.id"))
    business_name: Mapped[str] = mapped_column(String(200))
    business_number: Mapped[str | None] = mapped_column(String(20))
    representative: Mapped[str | None] = mapped_column(String(100))
    contact_phone: Mapped[str | None] = mapped_column(String(40))
    contact_email: Mapped[str | None] = mapped_column(String(200))
    kakao_channel_id: Mapped[str | None] = mapped_column(String(100))
    is_corporation: Mapped[bool] = mapped_column(Boolean, default=False)  # 법인/개인 구분 (A01/A02)
    file_password: Mapped[bytes | None] = mapped_column(LargeBinary)  # 암호화 첨부파일 비밀번호 (AES 암호화 저장)
    invite_sent: Mapped[bool] = mapped_column(Boolean, default=False)  # 초대장 발송 여부

    tax_office: Mapped[TaxOffice] = relationship()

    @property
    def collect_email(self) -> str:
        """거래처 전용 수신 이메일 주소 (collect+{full_id}@taxflow.ai)."""
        return f"collect+{self.id}@{COLLECT_EMAIL_DOMAIN}"
