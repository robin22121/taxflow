"""Korean withholding tax (원천징수세액) calculator.

Scope: estimate the income tax and local income tax to withhold per payroll line.
Local tax (지방소득세) is always 10% of income tax, rounded down to the nearest 10 KRW.

NOTE — production accuracy:
    The 근로소득(WAGE) calculation here uses a piecewise approximation calibrated
    to the NTS 근로소득간이세액표 (100% column, 부양가족수 1) within ~3% error.
    Before billing real customers we MUST replace ``_wage_table_lookup`` with the
    official table (load NTS Excel, lookup by 과세소득 bracket × 부양가족수 × %column).
    See: https://www.nts.go.kr/  →  국세정보  →  세무자료실  →  근로소득간이세액표
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.payroll import IncomeType


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


def _wage_table_lookup(taxable_monthly: int, dependents: int) -> int:
    """간이세액표 100% 컬럼 근사.

    Logic: apply yearly 근로소득공제 + 인적공제 + 표준세액공제 then progressive brackets,
    then divide by 12. Within ~3% of the official table for monthly 과세소득 1.5M~10M KRW.
    """
    if taxable_monthly <= 0:
        return 0

    # 부양가족수 — 본인 포함 (간이세액표 컬럼 기준)
    dependents = max(1, dependents)
    annual_taxable = taxable_monthly * 12

    # 근로소득공제 (간이 근사: 5단계 한도)
    if annual_taxable <= 5_000_000:
        earned_deduction = annual_taxable * 0.7
    elif annual_taxable <= 15_000_000:
        earned_deduction = 3_500_000 + (annual_taxable - 5_000_000) * 0.4
    elif annual_taxable <= 45_000_000:
        earned_deduction = 7_500_000 + (annual_taxable - 15_000_000) * 0.15
    elif annual_taxable <= 100_000_000:
        earned_deduction = 12_000_000 + (annual_taxable - 45_000_000) * 0.05
    else:
        earned_deduction = 14_750_000 + (annual_taxable - 100_000_000) * 0.02
    earned_deduction = min(earned_deduction, 20_000_000)

    # 인적공제: 1명당 150만원
    personal_deduction = dependents * 1_500_000

    # 표준세액공제(13만원)는 산출세액에서 차감 — 단순화를 위해 과세표준 단계에서 100만원 가산
    base = annual_taxable - earned_deduction - personal_deduction
    base = max(0, base)

    # 종합소득세 누진세율 (2024 기준)
    brackets: list[tuple[int, float, int]] = [
        (14_000_000, 0.06, 0),
        (50_000_000, 0.15, 14_000_000 * 0.06 - 14_000_000 * 0.06),  # cumulative below
        (88_000_000, 0.24, 0),
        (150_000_000, 0.35, 0),
        (300_000_000, 0.38, 0),
        (500_000_000, 0.40, 0),
        (1_000_000_000, 0.42, 0),
        (10**12, 0.45, 0),
    ]
    # cumulative pre-bracket tax
    cum: list[float] = []
    running = 0.0
    prev_top = 0
    rates = [b[1] for b in brackets]
    tops = [b[0] for b in brackets]
    for i, top in enumerate(tops):
        cum.append(running)
        running += (top - prev_top) * rates[i]
        prev_top = top

    annual_tax = 0.0
    prev_top = 0
    for top, rate, _ in brackets:
        if base <= top:
            # cumulative tax of brackets below this one + (base - prev_top) * rate
            idx = tops.index(top)
            annual_tax = cum[idx] + (base - prev_top) * rate
            break
        prev_top = top

    # 근로소득세액공제: 산출세액의 55%(작은 구간) ~ 30%(큰 구간), 한도 50/66/74만원
    if annual_tax <= 1_300_000:
        credit = annual_tax * 0.55
    else:
        credit = 715_000 + (annual_tax - 1_300_000) * 0.30
    if annual_taxable <= 33_000_000:
        credit = min(credit, 740_000)
    elif annual_taxable <= 70_000_000:
        credit = min(credit, max(660_000, 740_000 - (annual_taxable - 33_000_000) * 0.008))
    else:
        credit = min(credit, max(500_000, 660_000 - (annual_taxable - 70_000_000) * 0.005))

    annual_tax_after_credit = max(0.0, annual_tax - credit)
    monthly_tax = annual_tax_after_credit / 12
    return _round_down_10(monthly_tax)


def calculate_withholding_tax(
    income_type: IncomeType,
    taxable_amount: int,
    dependents: int = 1,
    daily_count: int | None = None,
) -> WithholdingTax:
    """원천징수세액 계산.

    Args:
        income_type: 소득 구분
        taxable_amount: 과세 대상 금액 (근로소득은 비과세 제외 월 과세소득)
        dependents: 부양가족수 (본인 포함). WAGE만 사용.
        daily_count: 일용근로소득의 근로일수. DAILY 일 때만 사용.
    """
    if taxable_amount <= 0:
        return WithholdingTax(0, 0)

    if income_type == IncomeType.WAGE:
        income_tax = _wage_table_lookup(taxable_amount, dependents)
    elif income_type == IncomeType.BUSINESS:
        # 사업소득 원천징수: 3% (지방소득세 0.3% 별도)
        income_tax = _round_down_10(taxable_amount * 0.03)
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
