"""근로소득 간이세액표 조회 회귀 테스트.

기준값은 소득세법 시행령 [별표2] <개정 2026. 2. 27.> 원문과, 실제 세무사사무소가
제출한 급여대장(주식회사 동문 2025-11월분) 실측 원천징수액이다.
"""

import pytest

from app.models.payroll import IncomeType
from app.services.tax_calc import calculate_withholding_tax
from app.services.wage_tax_table import lookup_wage_tax


# 실무 급여대장 실측값 — (과세 월급여, 공제대상가족수, 소득세, 지방소득세)
REAL_PAYROLL = [
    (2_100_000, 1, 22_740, 2_270),  # 백재봉·김영희·염희정·최경화
    (2_600_000, 1, 39_690, 3_960),  # 석란
    (1_700_000, 1, 13_050, 1_300),  # 오은서
]


@pytest.mark.parametrize("wage,deps,income_tax,local_tax", REAL_PAYROLL)
def test_matches_real_payroll_register(wage, deps, income_tax, local_tax):
    assert lookup_wage_tax(wage, deps) == income_tax
    wt = calculate_withholding_tax(IncomeType.WAGE, wage, dependents=deps)
    assert (wt.income_tax, wt.local_tax) == (income_tax, local_tax)


def test_bracket_is_half_open_on_thousand_won():
    """구간은 [하한, 상한) — 2,100천원 이상 2,110천원 미만이 같은 세액."""
    assert lookup_wage_tax(2_100_000, 1) == 22_740
    assert lookup_wage_tax(2_109_999, 1) == 22_740
    assert lookup_wage_tax(2_110_000, 1) == 23_060


def test_dependent_columns():
    """별표2 제6호 표 2,100~2,110천원 행: 가족수 1~6명."""
    expected = [22_740, 16_810, 8_580, 5_210, 1_830, 0]
    assert [lookup_wage_tax(2_100_000, d) for d in range(1, 7)] == expected


def test_below_table_floor_is_zero():
    assert lookup_wage_tax(700_000, 1) == 0
    assert lookup_wage_tax(0, 1) == 0
    assert lookup_wage_tax(-1, 1) == 0


def test_children_default_to_none():
    """자녀 자료가 없으면 자녀 0명으로 본다 — 표 금액에서 아무것도 빼지 않는다."""
    assert lookup_wage_tax(2_100_000, 1) == lookup_wage_tax(2_100_000, 1, children=0)
    assert lookup_wage_tax(2_100_000, 1) == 22_740

    # 공개 진입점도 동일하게 자녀 0명이 기본값이다.
    wt = calculate_withholding_tax(IncomeType.WAGE, 2_100_000, dependents=1)
    assert wt.income_tax == 22_740
    with_children = calculate_withholding_tax(
        IncomeType.WAGE, 2_100_000, dependents=1, children=1
    )
    assert with_children.income_tax == 22_740 - 20_830


def test_child_credit_deducts_and_floors_at_zero():
    """별표2 제3호 — 8세 이상 20세 이하 자녀 공제, 음수면 0원."""
    assert lookup_wage_tax(2_100_000, 1, children=1) == 22_740 - 20_830
    assert lookup_wage_tax(2_100_000, 1, children=2) == 0  # 45,830 > 22,740
    # 3명 이상: 45,830 + 2명 초과 1명당 33,330
    assert lookup_wage_tax(10_000_000, 1, children=3) == 1_507_400 - (45_830 + 33_330)


def test_dependents_over_eleven():
    """별표2 제4호 — 11명 초과분은 (10명 세액 - 11명 세액)만큼 추가 차감."""
    d10, d11 = 990_840, 960_840
    assert lookup_wage_tax(10_000_000, 10) == d10
    assert lookup_wage_tax(10_000_000, 11) == d11
    assert lookup_wage_tax(10_000_000, 12) == d11 - (d10 - d11)
    assert lookup_wage_tax(10_000_000, 13) == d11 - (d10 - d11) * 2


def test_above_table_max_uses_formula():
    """별표2 제6호 — 10,000천원 초과 ~ 14,000천원 이하 구간."""
    anchor = 1_507_400
    expected = anchor + 25_000 + int((2_000_000 * 0.98 * 0.35) // 10) * 10
    assert lookup_wage_tax(12_000_000, 1) == expected

    # 14,000천원 초과 구간은 정액 1,397,000원 + 초과분 98%의 38%
    expected14 = anchor + int((1_397_000 + 1_000_000 * 0.98 * 0.38) // 10) * 10
    assert lookup_wage_tax(15_000_000, 1) == expected14


def test_table_is_continuous_and_covers_full_range():
    """CSV 파싱 무결성 — 구간이 770천원부터 빈틈없이 이어져야 한다."""
    from app.services.wage_tax_table import _table

    lows, taxes = _table()
    assert lows[0] == 770
    assert lows[-1] == 10_000
    assert len(lows) == len(taxes)
    assert all(b > a for a, b in zip(lows, lows[1:]))
    assert all(len(row) == 11 for row in taxes)
    # 같은 행 안에서 가족수가 늘수록 세액이 줄어든다(같거나).
    assert all(all(a >= b for a, b in zip(row, row[1:])) for row in taxes)
