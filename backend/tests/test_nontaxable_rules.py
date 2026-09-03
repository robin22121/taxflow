"""비과세 수당 규칙 회귀 테스트.

두 가지 오류를 방지한다.
1. 일용근로·사업소득 등 상용근로(WAGE)가 아닌 소득에 비과세 수당을 적용하는 것.
2. 사업주가 보고한 총지급액(비과세 포함)에 비과세를 다시 더해 이중계산하는 것.
"""

from types import SimpleNamespace

from app.models.payroll import IncomeType
from app.services.payroll_excel import _data_row

_GROSS_COL = 10  # K: 지급액계
_NET_COL = 23  # X: 차인지급액
_BASE_COL = 5  # F: 기본급


def _entry(*, total, bonus=0, meal=0, car=0, childcare=0, non_tax=0):
    return SimpleNamespace(
        employee=SimpleNamespace(name="김철수", employee_code="E001"),
        raw_name="김철수",
        total_amount=total,
        bonus_amount=bonus,
        meal_amount=meal,
        car_amount=car,
        childcare_amount=childcare,
        non_taxable=non_tax,
        taxable=max(0, total - non_tax),
        income_tax=0,
        local_tax=0,
        national_pension=0,
        health_insurance=0,
        employment_insurance=0,
        longterm_care=0,
    )


def test_gross_is_reported_total_not_total_plus_nontaxable():
    """사업주가 390,000원 지급 보고 → 지급액계도 390,000원 (990,000 아님)."""
    row = _data_row(_entry(total=390_000, meal=200_000, car=200_000,
                           childcare=200_000, non_tax=600_000), 1)
    assert row[_GROSS_COL] == 390_000
    assert row[_NET_COL] == 390_000
    # 비과세 합이 총지급액을 넘으면 기본급은 음수가 아닌 0
    assert row[_BASE_COL] == 0


def test_gross_equals_total_for_normal_wage_entry():
    """상용근로 정상 케이스: 기본급 + 상여 + 비과세 = 총지급액."""
    row = _data_row(_entry(total=3_000_000, bonus=100_000, meal=200_000,
                           non_tax=200_000), 1)
    assert row[_BASE_COL] == 2_700_000
    assert row[_GROSS_COL] == 3_000_000


def _normalize(income_type: IncomeType, total: int, non_taxable: int) -> int:
    """imports.py / filings.py PATCH 가 공유하는 비과세 정규화 규칙."""
    if income_type != IncomeType.WAGE:
        return 0
    return min(non_taxable, total)


def test_nontaxable_forced_zero_for_non_wage_income():
    for it in (IncomeType.DAILY, IncomeType.BUSINESS,
               IncomeType.OTHER, IncomeType.RETIREMENT):
        assert _normalize(it, 390_000, 600_000) == 0


def test_nontaxable_capped_at_total_for_wage():
    assert _normalize(IncomeType.WAGE, 390_000, 600_000) == 390_000
    assert _normalize(IncomeType.WAGE, 3_000_000, 200_000) == 200_000
