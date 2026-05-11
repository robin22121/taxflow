import enum
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Index, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.client import Client


class EmploymentStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    RESIGNED = "RESIGNED"
    PENDING = "PENDING"  # 신규 의심 → 주민번호 등 미수집


class Employee(Base, IdMixin, TimestampMixin):
    """거래처의 직원 마스터."""

    __tablename__ = "employees"
    __table_args__ = (
        Index("ix_employees_client", "client_id"),
        Index("ix_employees_client_name", "client_id", "name"),
    )

    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    name: Mapped[str] = mapped_column(String(100))
    rrn_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    rrn_last4: Mapped[str | None] = mapped_column(String(4))  # 마스킹 표시용
    employee_code: Mapped[str | None] = mapped_column(String(40))
    wehago_employee_id: Mapped[str | None] = mapped_column(String(40))
    business_type_code: Mapped[str | None] = mapped_column(String(10))  # 사업소득 업종코드 (940100~940929)
    hired_at: Mapped[date | None] = mapped_column(Date)
    resigned_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[EmploymentStatus] = mapped_column(
        Enum(EmploymentStatus, native_enum=False, length=20),
        default=EmploymentStatus.ACTIVE,
    )

    client: Mapped[Client] = relationship()
