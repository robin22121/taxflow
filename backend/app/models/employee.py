import enum
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Index, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.client import Client
from app.models.income_type import IncomeType


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
    # 급여대장 표기용 (위하고T 양식 C·D·E열)
    department: Mapped[str | None] = mapped_column(String(50))   # 부서
    position: Mapped[str | None] = mapped_column(String(50))     # 직급
    job_type: Mapped[str | None] = mapped_column(String(50))     # 직종
    wehago_employee_id: Mapped[str | None] = mapped_column(String(40))
    business_type_code: Mapped[str | None] = mapped_column(String(10))  # 사업소득 업종코드 (940100~940929)
    hired_at: Mapped[date | None] = mapped_column(Date)
    resigned_at: Mapped[date | None] = mapped_column(Date)
    # 간이세액표 계산용 (위하고 T 사원등록 공제탭과 대응, plan/16 §13-1)
    dependents_count: Mapped[int] = mapped_column(Integer, default=1)      # 공제대상가족수 (본인 포함)
    children_count: Mapped[int] = mapped_column(Integer, default=0)       # 8세 이상 20세 이하 자녀 수
    withholding_rate_adjust: Mapped[int] = mapped_column(Integer, default=100)  # 조정율 80/100/120(%)
    status: Mapped[EmploymentStatus] = mapped_column(
        Enum(EmploymentStatus, native_enum=False, length=20),
        default=EmploymentStatus.ACTIVE,
    )
    # 소득구분 (plan/02-data-model.md — 근로/사업/기타/일용/퇴직). 영세사업장 대다수가
    # 근로소득만 다루므로 기본값 WAGE (신규 필드는 항상 기본값 우선, 필수입력 강제 금지).
    income_type: Mapped[IncomeType] = mapped_column(
        Enum(IncomeType, native_enum=False, length=20),
        default=IncomeType.WAGE,
    )

    client: Mapped[Client] = relationship()
