"""Korean withholding tax (원천징수세액) calculator.

Scope: estimate the income tax and local income tax to withhold per payroll line.
Local tax (지방소득세) is always 10% of income tax, rounded down to the nearest 10 KRW.

근로소득(WAGE)은 소득세법 시행령 [별표2] 근로소득간이세액표 원문을 그대로 조회한다
(``app.services.wage_tax_table``). 그 밖의 소득구분은 아래 근사 세율을 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.payroll import IncomeType
from app.services.wage_tax_table import lookup_wage_tax


@dataclass(frozen=True, slots=True)
class WithholdingTax:
    income_tax: int
    local_tax: int

    @property
    def total(self) -> int:
        return self.income_tax + self.local_tax


def _round_down_10(amount: float) -> int:
    """원천징수 관행상 10원 단위 절사."""
    return int(amount // 10) * 10


def _local_tax(income_tax: int) -> int:
    return _round_down_10(income_tax * 0.1)


def _wage_table_lookup(taxable_monthly: int, dependents: int, children: int = 0) -> int:
    """간이세액표(100% 컬럼) 조회 — 소득세법 시행령 [별표2] 원문 기준."""
    return lookup_wage_tax(taxable_monthly, dependents, children)


# ---------------------------------------------------------------------------
# 사업소득 업종별 세율
# ---------------------------------------------------------------------------

# 기본 3%. 예외: 봉사료수취자(940905) 5%, 외국인 직업운동가(940904) 20%
_BUSINESS_SPECIAL_RATES: dict[str, float] = {
    "940905": 0.05,  # 봉사료수취자
    # 940904 직업운동가 — 외국인 3년이하 계약 시 20%, 그 외 3%
    # 외국인 여부는 Employee에서 판단해야 하므로 여기서는 기본 3%,
    # 20%가 필요한 경우 호출자가 business_type_code="940904_foreign"으로 전달
    "940904_foreign": 0.20,
}

_DEFAULT_BUSINESS_RATE = 0.03


def _business_tax_rate(business_type_code: str | None) -> float:
    """사업소득 업종코드별 세율 반환."""
    if business_type_code and business_type_code in _BUSINESS_SPECIAL_RATES:
        return _BUSINESS_SPECIAL_RATES[business_type_code]
    return _DEFAULT_BUSINESS_RATE


def calculate_withholding_tax(
    income_type: IncomeType,
    taxable_amount: int,
    dependents: int = 1,
    children: int = 0,
    daily_count: int | None = None,
    business_type_code: str | None = None,
) -> WithholdingTax:
    """원천징수세액 계산.

    Args:
        income_type: 소득 구분
        taxable_amount: 과세 대상 금액 (근로소득은 비과세 제외 월 과세소득)
        dependents: 공제대상가족의 수 (본인 포함). WAGE만 사용.
        children: 공제대상가족 중 8세 이상 20세 이하 자녀 수. WAGE만 사용.
            기본값 0 — 자녀 신고 자료가 없으면 자녀가 없는 것으로 본다.
            (자녀가 있으면 세액이 줄어드므로, 0은 과소징수가 아닌 안전한 쪽이다.)
        daily_count: 일용근로소득의 근로일수. DAILY 일 때만 사용.
        business_type_code: 사업소득 업종코드. BUSINESS일 때 세율 분기용.
    """
    if taxable_amount <= 0:
        return WithholdingTax(0, 0)

    if income_type == IncomeType.WAGE:
        income_tax = _wage_table_lookup(taxable_amount, dependents, children)
    elif income_type == IncomeType.BUSINESS:
        rate = _business_tax_rate(business_type_code)
        income_tax = _round_down_10(taxable_amount * rate)
    elif income_type == IncomeType.OTHER:
        # 기타소득: 필요경비 60% 의제 → 기타소득금액의 20%
        # 결과적으로 지급액 대비 8%
        tax_base = taxable_amount * 0.4
        income_tax = _round_down_10(tax_base * 0.20)
    elif income_type == IncomeType.DAILY:
        # 일용근로소득: (일급 - 150,000) * 6% * (1 - 0.55) = (일급 - 150,000) * 2.7%
        # taxable_amount은 합산 지급액 → daily_count로 일급 환산
        days = max(1, daily_count or 1)
        per_day = taxable_amount / days
        per_day_taxable = max(0.0, per_day - 150_000)
        per_day_tax = per_day_taxable * 0.06 * 0.45
        income_tax = _round_down_10(per_day_tax * days)
    elif income_type == IncomeType.RETIREMENT:
        # 퇴직소득세는 근속연수공제·환산급여·특별공제가 필요 → 별도 모듈에서 처리.
        # MVP에서는 0 반환 + 검증 단계에서 경고 표시.
        income_tax = 0
    else:
        income_tax = 0

    return WithholdingTax(income_tax=income_tax, local_tax=_local_tax(income_tax))


# ---------------------------------------------------------------------------
# A코드 매핑 (원천징수이행상황신고서용)
# ---------------------------------------------------------------------------

def income_type_to_a_code(t: IncomeType, is_corporation: bool = False) -> str:
    """IncomeType → 국세청 원천징수이행상황신고서 A코드."""
    if t == IncomeType.WAGE:
        return "A01" if is_corporation else "A02"
    return {
        IncomeType.DAILY: "A03",
        IncomeType.BUSINESS: "A25",
        IncomeType.OTHER: "A42",
        IncomeType.RETIREMENT: "A22",
    }.get(t, "A99")


def income_type_to_wehago_code(t: IncomeType) -> str:
    """위하고T 일괄등록 양식의 소득구분코드 (실제 양식 검증 필요)."""
    # TODO: 위하고T 양식 실측 후 정확한 코드로 교체.
    return {
        IncomeType.WAGE: "A01",
        IncomeType.BUSINESS: "A03",
        IncomeType.OTHER: "A04",
        IncomeType.DAILY: "A02",
        IncomeType.RETIREMENT: "A20",
    }[t]


# ---------------------------------------------------------------------------
# 4대보험 (사용자 부담분) — 2026년 기준 근사
# ---------------------------------------------------------------------------
# Rates are policy-driven and updated annually by NPS / NHIS / 고용노동부.
# Verify against the latest official notice before billing real customers.

_NPS_RATE = 0.045              # 국민연금 사용자 부담
_NPS_MIN_BASE = 370_000        # 기준소득월액 하한
_NPS_MAX_BASE = 5_900_000      # 기준소득월액 상한
_HI_RATE = 0.03545             # 건강보험 사용자 부담
_LTC_RATE_OF_HI = 0.1295       # 장기요양 = 건보료 × 12.95%
_EI_RATE = 0.009               # 고용보험 실업급여


@dataclass(frozen=True, slots=True)
class SocialInsurance:
    national_pension: int
    health_insurance: int
    employment_insurance: int
    longterm_care: int

    @property
    def total(self) -> int:
        return (
            self.national_pension
            + self.health_insurance
            + self.employment_insurance
            + self.longterm_care
        )


def calculate_social_insurance(
    monthly_wage: int,
    income_type: IncomeType = IncomeType.WAGE,
) -> SocialInsurance:
    """4대보험 사용자 부담분 계산 (근로소득 기준).

    근로소득 외 소득구분은 일반적으로 4대보험 미가입 → 0 반환.
    사업장별 가입 여부·감면 대상은 추후 Client/Employee 옵션으로 분기.
    """
    if income_type != IncomeType.WAGE or monthly_wage <= 0:
        return SocialInsurance(0, 0, 0, 0)

    nps_base = max(_NPS_MIN_BASE, min(_NPS_MAX_BASE, monthly_wage))
    nps = _round_down_10(nps_base * _NPS_RATE)
    hi = _round_down_10(monthly_wage * _HI_RATE)
    ltc = _round_down_10(hi * _LTC_RATE_OF_HI)
    ei = _round_down_10(monthly_wage * _EI_RATE)
    return SocialInsurance(
        national_pension=nps,
        health_insurance=hi,
        employment_insurance=ei,
        longterm_care=ltc,
    )


# Default rates exposed so callers (e.g. API "system defaults" endpoint) can echo them back.
DEFAULT_NPS_RATE = _NPS_RATE
DEFAULT_HI_RATE = _HI_RATE
DEFAULT_LTC_RATE_OF_HI = _LTC_RATE_OF_HI
DEFAULT_EI_RATE = _EI_RATE


def calculate_social_insurance_with_overrides(
    monthly_wage: int,
    income_type: IncomeType = IncomeType.WAGE,
    *,
    apply_national_pension: bool = True,
    apply_health_insurance: bool = True,
    apply_employment_insurance: bool = True,
    apply_longterm_care: bool = True,
    nps_rate: float | None = None,
    hi_rate: float | None = None,
    ltc_rate_of_hi: float | None = None,
    ei_rate: float | None = None,
) -> SocialInsurance:
    """4대보험 — 거래처 세팅(apply 플래그 + 요율 오버라이드) 반영 버전.

    plan.md 3.8절. ClientPayrollDefault 적용 진입점. Rate 인자는 백분율이 아닌 실수
    (예: 0.045). None이면 시스템 기본 요율 사용. apply_* 가 False면 해당 보험은 0원.
    """
    if income_type != IncomeType.WAGE or monthly_wage <= 0:
        return SocialInsurance(0, 0, 0, 0)

    nps_r = nps_rate if nps_rate is not None else _NPS_RATE
    hi_r = hi_rate if hi_rate is not None else _HI_RATE
    ltc_r = ltc_rate_of_hi if ltc_rate_of_hi is not None else _LTC_RATE_OF_HI
    ei_r = ei_rate if ei_rate is not None else _EI_RATE

    nps_base = max(_NPS_MIN_BASE, min(_NPS_MAX_BASE, monthly_wage))
    nps = _round_down_10(nps_base * nps_r) if apply_national_pension else 0
    hi = _round_down_10(monthly_wage * hi_r) if apply_health_insurance else 0
    # 장기요양은 건강보험료 기준 — 건보 미적용 시 자동 0
    ltc = _round_down_10(hi * ltc_r) if (apply_longterm_care and hi > 0) else 0
    ei = _round_down_10(monthly_wage * ei_r) if apply_employment_insurance else 0
    return SocialInsurance(
        national_pension=nps,
        health_insurance=hi,
        employment_insurance=ei,
        longterm_care=ltc,
    )
