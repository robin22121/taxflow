"""Tax calc smoke tests.

These verify the *direction* of the calculation and the deterministic non-WAGE
formulas exactly. WAGE is approximate so we only assert ranges.
"""

from app.models.payroll import IncomeType
from app.services.tax_calc import calculate_withholding_tax


def test_business_income_3_3_percent():
    r = calculate_withholding_tax(IncomeType.BUSINESS, 1_000_000)
    assert r.income_tax == 30_000
    assert r.local_tax == 3_000


def test_other_income_8_8_percent():
    r = calculate_withholding_tax(IncomeType.OTHER, 1_000_000)
    # base = 400,000; tax = 80,000
    assert r.income_tax == 80_000
    assert r.local_tax == 8_000


def test_daily_wage_below_threshold_is_zero():
    r = calculate_withholding_tax(IncomeType.DAILY, 140_000, daily_count=1)
    assert r.income_tax == 0


def test_daily_wage_above_threshold():
    # 일급 200,000 1일 → (200,000-150,000)*0.027 = 1,350 → 절사 1,350
    r = calculate_withholding_tax(IncomeType.DAILY, 200_000, daily_count=1)
    assert r.income_tax == 1_350


def test_wage_low_income_zero_or_low():
    # 월 1,000,000 → 연 12,000,000.
    # 공식 간이세액표는 0이지만, 우리 근사는 과소공제로 약간의 세액이 잡힘 (최대 1만원).
    # 실서비스 전 NTS 표 교체 시 0이 되어야 함.
    r = calculate_withholding_tax(IncomeType.WAGE, 1_000_000, dependents=1)
    assert r.income_tax < 15_000


def test_wage_mid_income_nonzero():
    # 월 3,000,000 → 약 70,000~120,000원 수준
    r = calculate_withholding_tax(IncomeType.WAGE, 3_000_000, dependents=1)
    assert 30_000 < r.income_tax < 200_000
    # 지방소득세는 income_tax의 10% 절사
    assert r.local_tax == r.income_tax // 100 * 10


def test_wage_dependents_reduces_tax():
    one = calculate_withholding_tax(IncomeType.WAGE, 4_000_000, dependents=1)
    four = calculate_withholding_tax(IncomeType.WAGE, 4_000_000, dependents=4)
    assert four.income_tax < one.income_tax


def test_zero_amount():
    r = calculate_withholding_tax(IncomeType.WAGE, 0)
    assert r.income_tax == 0
    assert r.local_tax == 0
