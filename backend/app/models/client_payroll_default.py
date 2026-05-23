from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.client import Client


class ClientPayrollDefault(Base, IdMixin, TimestampMixin):
    """거래처별 지급항목·4대보험 기본 세팅값.

    원시파일에 항목이 없을 때 fallback으로 사용. (plan.md 3.8절)

    요율 컬럼은 모두 nullable — null이면 tax_calc.py의 시스템 기본 요율을 사용.
    저장은 백분율(예: 4.5)로 하고, 계산 시점에 /100을 적용한다.
    """

    __tablename__ = "client_payroll_defaults"

    client_id: Mapped[str] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"),
        unique=True,
    )

    # 비과세 지급항목 기본금액 (원). 식대·자가운전은 비과세 한도(200,000) 시드,
    # 육아수당은 거래처마다 정책 편차가 커 0원 시드 (세무사가 명시 입력).
    meal_default: Mapped[int] = mapped_column(Integer, default=200_000)
    car_default: Mapped[int] = mapped_column(Integer, default=200_000)
    childcare_default: Mapped[int] = mapped_column(Integer, default=0)

    # 4대보험 적용 여부 (False면 0원 처리)
    apply_national_pension: Mapped[bool] = mapped_column(Boolean, default=True)
    apply_health_insurance: Mapped[bool] = mapped_column(Boolean, default=True)
    apply_employment_insurance: Mapped[bool] = mapped_column(Boolean, default=True)
    apply_longterm_care: Mapped[bool] = mapped_column(Boolean, default=True)

    # 요율 오버라이드 (백분율, null이면 시스템 기본 요율 사용)
    nps_rate_override: Mapped[float | None] = mapped_column(Numeric(6, 4))
    hi_rate_override: Mapped[float | None] = mapped_column(Numeric(6, 4))
    ltc_rate_override: Mapped[float | None] = mapped_column(Numeric(6, 4))
    ei_rate_override: Mapped[float | None] = mapped_column(Numeric(6, 4))

    # 정부 지원·비고 (두루누리 등)
    note: Mapped[str | None] = mapped_column(String(500))

    client: Mapped[Client] = relationship()
