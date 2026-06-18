import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import Base, IdMixin, TimestampMixin


class OfficeApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"    # 가입 후 서버 관리자 승인 대기
    APPROVED = "APPROVED"  # 승인 완료 — 사이트 이용 가능
    REJECTED = "REJECTED"  # 가입 거부


class CustomerClass(str, enum.Enum):
    TRIAL = "TRIAL"      # 무료 체험
    REGULAR = "REGULAR"  # 정식 고객
    VIP = "VIP"          # 우대 고객
    CHURNED = "CHURNED"  # 해지


class TaxOffice(Base, IdMixin, TimestampMixin):
    __tablename__ = "tax_offices"

    name: Mapped[str] = mapped_column(String(200))
    short_code: Mapped[str | None] = mapped_column(String(20), unique=True)
    business_number: Mapped[str | None] = mapped_column(String(20))
    representative: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(500))

    # ── 서버 관리자 회원 관리 필드 ──────────────────────────
    approval_status: Mapped[OfficeApprovalStatus] = mapped_column(
        Enum(OfficeApprovalStatus, native_enum=False, length=20),
        default=OfficeApprovalStatus.PENDING,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    customer_class: Mapped[CustomerClass] = mapped_column(
        Enum(CustomerClass, native_enum=False, length=20),
        default=CustomerClass.TRIAL,
    )
    subscription_start: Mapped[date | None] = mapped_column(Date)  # 결제기간 시작
    subscription_end: Mapped[date | None] = mapped_column(Date)    # 결제기간 종료
    admin_memo: Mapped[str | None] = mapped_column(String(1000))   # 관리자 메모

    def __repr__(self) -> str:
        return f"<TaxOffice {self.name}>"
