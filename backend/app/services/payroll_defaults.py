"""거래처별 지급항목·4대보험 기본 세팅 로딩 + 적용 헬퍼 (plan.md 3.8)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClientPayrollDefault
from app.models.payroll import IncomeType
from app.services.tax_calc import (
    SocialInsurance,
    calculate_social_insurance_with_overrides,
)


@dataclass(frozen=True, slots=True)
class ResolvedPayrollDefaults:
    """ClientPayrollDefault → 적용에 필요한 값만 평탄화. 레코드가 없으면 시스템 기본값."""

    meal_default: int = 200_000
    car_default: int = 200_000
    childcare_default: int = 200_000
    apply_national_pension: bool = True
    apply_health_insurance: bool = True
    apply_employment_insurance: bool = True
    apply_longterm_care: bool = True
    nps_rate: float | None = None  # None → 시스템 기본 요율 (tax_calc)
    hi_rate: float | None = None
    ltc_rate: float | None = None
    ei_rate: float | None = None

    @classmethod
    def from_row(cls, row: ClientPayrollDefault | None) -> "ResolvedPayrollDefaults":
        if row is None:
            return cls()
        return cls(
            meal_default=row.meal_default,
            car_default=row.car_default,
            childcare_default=row.childcare_default,
            apply_national_pension=row.apply_national_pension,
            apply_health_insurance=row.apply_health_insurance,
            apply_employment_insurance=row.apply_employment_insurance,
            apply_longterm_care=row.apply_longterm_care,
            nps_rate=float(row.nps_rate_override) if row.nps_rate_override is not None else None,
            hi_rate=float(row.hi_rate_override) if row.hi_rate_override is not None else None,
            ltc_rate=float(row.ltc_rate_override) if row.ltc_rate_override is not None else None,
            ei_rate=float(row.ei_rate_override) if row.ei_rate_override is not None else None,
        )

    def social_insurance(self, monthly_wage: int, income_type: IncomeType) -> SocialInsurance:
        return calculate_social_insurance_with_overrides(
            monthly_wage=monthly_wage,
            income_type=income_type,
            apply_national_pension=self.apply_national_pension,
            apply_health_insurance=self.apply_health_insurance,
            apply_employment_insurance=self.apply_employment_insurance,
            apply_longterm_care=self.apply_longterm_care,
            nps_rate=self.nps_rate,
            hi_rate=self.hi_rate,
            ltc_rate_of_hi=self.ltc_rate,
            ei_rate=self.ei_rate,
        )


async def load_payroll_defaults(db: AsyncSession, client_id: str) -> ResolvedPayrollDefaults:
    row = (
        await db.execute(
            select(ClientPayrollDefault).where(ClientPayrollDefault.client_id == client_id)
        )
    ).scalar_one_or_none()
    return ResolvedPayrollDefaults.from_row(row)
