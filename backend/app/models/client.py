from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, String
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
    # 세목 속성 — 신고안내 대상 필터 (plan/13-messaging-activation.md §5.3)
    vat_type: Mapped[str | None] = mapped_column(String(20))  # GENERAL | SIMPLIFIED | EXEMPT
    withholding_semiannual: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    fiscal_year_end_month: Mapped[int | None] = mapped_column(Integer)  # 법인 결산월 (None = 12월)
    sincere_filing: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")  # 성실신고 대상
    # 사업장 기본사항 — 위하고 수임처정보에서 가져온다 (plan/16 §12)
    business_type: Mapped[str | None] = mapped_column(String(100))   # 업태
    business_item: Mapped[str | None] = mapped_column(String(200))   # 종목(업종)
    business_address: Mapped[str | None] = mapped_column(String(300))  # 사업장 주소
    wehago_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 마지막 위하고 임포트
    # 사업주 포털 PIN (plan/12-owner-portal.md §4.3.3) — None이면 게이트 뒤 구역을 노출하지 않는다
    portal_pin_hash: Mapped[str | None] = mapped_column(String(128))
    portal_pin_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    portal_pin_failed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    tax_office: Mapped[TaxOffice] = relationship()

    @property
    def collect_email(self) -> str:
        """거래처 전용 수신 이메일 주소 (collect+{full_id}@taxflow.ai)."""
        return f"collect+{self.id}@{COLLECT_EMAIL_DOMAIN}"
