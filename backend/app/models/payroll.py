import enum
from datetime import date

from sqlalchemy import JSON, Date, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.client import Client
from app.models.collection import CollectionSession
from app.models.employee import Employee
from app.models.monthly_filing import MonthlyFiling


class IncomeType(str, enum.Enum):
    WAGE = "WAGE"  # 근로소득
    BUSINESS = "BUSINESS"  # 사업소득
    OTHER = "OTHER"  # 기타소득
    DAILY = "DAILY"  # 일용근로소득
    RETIREMENT = "RETIREMENT"  # 퇴직소득


class MatchStatus(str, enum.Enum):
    MATCHED = "MATCHED"
    NEW_HIRE_SUSPECTED = "NEW_HIRE_SUSPECTED"
    RESIGNATION_SUSPECTED = "RESIGNATION_SUSPECTED"
    AMBIGUOUS = "AMBIGUOUS"


class PayrollEntry(Base, IdMixin, TimestampMixin):
    """월별 신고에 포함될 직원별 인건비 항목."""

    __tablename__ = "payroll_entries"
    __table_args__ = (
        Index("ix_payroll_filing", "monthly_filing_id"),
        Index("ix_payroll_session", "collection_session_id"),
        Index("ix_payroll_employee", "employee_id"),
    )

    monthly_filing_id: Mapped[str] = mapped_column(ForeignKey("monthly_filings.id"))
    collection_session_id: Mapped[str] = mapped_column(ForeignKey("collection_sessions.id"))
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"))

    raw_name: Mapped[str] = mapped_column(String(100))
    income_type: Mapped[IncomeType] = mapped_column(
        Enum(IncomeType, native_enum=False, length=20),
        default=IncomeType.WAGE,
    )

    # 국세청 A코드 (원천징수이행상황신고서용) — A01, A02, A03, A25, A42 등
    a_code: Mapped[str | None] = mapped_column(String(5))
    # 사업소득 업종코드 (간이지급명세서 사업소득용) — 940100~940929
    business_type_code: Mapped[str | None] = mapped_column(String(10))

    total_amount: Mapped[int] = mapped_column(Integer, default=0)
    salary_amount: Mapped[int | None] = mapped_column(Integer)  # 급여 (근로소득 간이지급명세서용)
    bonus_amount: Mapped[int | None] = mapped_column(Integer)  # 상여 (근로소득 간이지급명세서용)
    non_taxable: Mapped[int] = mapped_column(Integer, default=0)  # 비과세 합계
    # 비과세 세부 항목 (급여대장 양식용)
    meal_amount: Mapped[int] = mapped_column(Integer, default=0)         # 식대 (한도 20만)
    car_amount: Mapped[int] = mapped_column(Integer, default=0)          # 자가운전보조금 (한도 20만)
    childcare_amount: Mapped[int] = mapped_column(Integer, default=0)    # 육아수당 (한도 20만)
    taxable: Mapped[int] = mapped_column(Integer, default=0)
    # 4대보험 공제 (사용자 부담분)
    national_pension: Mapped[int] = mapped_column(Integer, default=0)    # 국민연금
    health_insurance: Mapped[int] = mapped_column(Integer, default=0)    # 건강보험
    employment_insurance: Mapped[int] = mapped_column(Integer, default=0)  # 고용보험
    longterm_care: Mapped[int] = mapped_column(Integer, default=0)       # 장기요양보험료
    income_tax: Mapped[int] = mapped_column(Integer, default=0)
    local_tax: Mapped[int] = mapped_column(Integer, default=0)
    payment_date: Mapped[date | None] = mapped_column(Date)
    dependents: Mapped[int] = mapped_column(Integer, default=1)  # 부양가족수 (간이세액표용)

    match_status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus, native_enum=False, length=30),
        default=MatchStatus.AMBIGUOUS,
    )
    prev_amount: Mapped[int | None] = mapped_column(Integer)
    anomaly_notes: Mapped[dict | None] = mapped_column(JSON)
    approved: Mapped[bool] = mapped_column(default=False)

    monthly_filing: Mapped[MonthlyFiling] = relationship()
    collection_session: Mapped[CollectionSession] = relationship()
    client: Mapped[Client] = relationship()
    employee: Mapped[Employee | None] = relationship()
