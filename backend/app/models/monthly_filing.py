import enum

from sqlalchemy import Enum, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.tax_office import TaxOffice


class MonthlyFilingStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    COLLECTING = "COLLECTING"
    REVIEWING = "REVIEWING"
    APPROVED = "APPROVED"
    EXCEL_GENERATED = "EXCEL_GENERATED"
    FILED = "FILED"
    COMPLETED = "COMPLETED"


class MonthlyFiling(Base, IdMixin, TimestampMixin):
    """원천세 월별 신고 — 세무사사무소 단위 한 달치 신고 묶음."""

    __tablename__ = "monthly_filings"
    __table_args__ = (
        UniqueConstraint("tax_office_id", "period", name="uq_filing_office_period"),
        Index("ix_filings_office", "tax_office_id"),
    )

    tax_office_id: Mapped[str] = mapped_column(ForeignKey("tax_offices.id"))
    period: Mapped[str] = mapped_column(String(7))  # "YYYY-MM"
    status: Mapped[MonthlyFilingStatus] = mapped_column(
        Enum(MonthlyFilingStatus, native_enum=False, length=20),
        default=MonthlyFilingStatus.DRAFT,
    )
    total_clients: Mapped[int] = mapped_column(Integer, default=0)
    total_entries: Mapped[int] = mapped_column(Integer, default=0)

    tax_office: Mapped[TaxOffice] = relationship()
