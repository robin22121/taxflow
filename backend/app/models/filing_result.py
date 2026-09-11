import enum
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.client import Client


class FilingResultSource(str, enum.Enum):
    MANUAL_UPLOAD = "MANUAL_UPLOAD"  # 세무사가 직접 올림
    RPA = "RPA"  # SmartA 에이전트가 적재 (Phase 2)


class ClientFilingResult(Base, IdMixin, TimestampMixin):
    """거래처 × 신고월의 신고 결과 — 보관함의 저장소 (plan/12-owner-portal.md §5.4).

    ``MonthlyFiling``은 ``tax_office_id + period`` 유니크라 **세무사사무소 한 달 묶음**이지
    거래처 단위가 아니다. 사장님에게 "우리 가게가 얼마 내야 하나"를 보여주려면
    거래처별 결과를 담을 곳이 따로 있어야 한다.

    여기 담기는 값은 **홈택스에서 돌아온 사실**뿐이다. 예상 납부세액은
    ``PayrollEntry.income_tax + local_tax`` 합계로 그때그때 계산하므로 저장하지 않는다
    (저장하면 급여 수정 후 stale 값이 남는다).
    """

    __tablename__ = "client_filing_results"
    __table_args__ = (
        UniqueConstraint("client_id", "period", name="uq_result_client_period"),
    )

    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    period: Mapped[str] = mapped_column(String(7))  # "YYYY-MM"

    settled_tax: Mapped[int | None] = mapped_column(Integer)  # 확정 납부세액 (홈택스 접수액)
    virtual_account: Mapped[str | None] = mapped_column(String(60))  # 가상계좌
    epayment_number: Mapped[str | None] = mapped_column(String(40))  # 전자납부번호
    due_date: Mapped[date | None] = mapped_column(Date)  # 납부기한

    receipt_key: Mapped[str | None] = mapped_column(String(255))  # 접수증 PDF
    receipt_name: Mapped[str | None] = mapped_column(String(255))
    payment_slip_key: Mapped[str | None] = mapped_column(String(255))  # 납부서 PDF
    payment_slip_name: Mapped[str | None] = mapped_column(String(255))

    source: Mapped[FilingResultSource] = mapped_column(
        Enum(FilingResultSource, native_enum=False, length=20),
        default=FilingResultSource.MANUAL_UPLOAD,
    )

    client: Mapped[Client] = relationship()
