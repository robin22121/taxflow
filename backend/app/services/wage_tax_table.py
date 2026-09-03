"""근로소득 간이세액표 조회.

소득세법 시행령 [별표2] 근로소득간이세액표(제189조제1항 관련) <개정 2026. 2. 27.> 원문을
``app/data/wage_tax_table_2026.csv`` 에 그대로 옮겨 담고, 별표2 각 호의 규정대로 조회한다.

- 제3호: 8세 이상 20세 이하 자녀 수별 세액공제 (공제 후 음수면 0원)
- 제4호: 공제대상가족의 수가 11명을 초과하는 경우의 산식
- 제6호: 월급여액이 10,000천원을 초과하는 경우의 산식
"""

from __future__ import annotations

import csv
from bisect import bisect_right
from functools import lru_cache
from pathlib import Path

_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "wage_tax_table_2026.csv"

# 표에 수록된 월급여액 상한(원). 이 금액을 초과하면 별표2 제6호 산식을 쓴다.
_TABLE_MAX_WAGE = 10_000_000


@lru_cache(maxsize=1)
def _table() -> tuple[tuple[int, ...], tuple[tuple[int, ...], ...]]:
    """(구간 하한 리스트, 구간별 공제대상가족수 1~11명 세액) — 천원 단위 하한."""
    lows: list[int] = []
    taxes: list[tuple[int, ...]] = []
    with _CSV_PATH.open(encoding="utf-8") as fp:
        for row in csv.reader(line for line in fp if not line.startswith("#")):
            if row[0] == "min_thousand":
                continue
            lows.append(int(row[0]))
            taxes.append(tuple(int(v) for v in row[2:]))
    return tuple(lows), tuple(taxes)


def _row_for(monthly_wage: int) -> tuple[int, ...] | None:
    """월급여액(원)이 속한 구간의 가족수별 세액. 표 범위 미만이면 None."""
    lows, taxes = _table()
    idx = bisect_right(lows, monthly_wage // 1000) - 1
    if idx < 0:
        return None
    return taxes[idx]


def _tax_for_dependents(row: tuple[int, ...], dependents: int) -> int:
    """별표2 제4호 — 공제대상가족의 수가 11명을 초과하면 10명·11명 세액의 차이만큼 더 뺀다."""
    if dependents <= 11:
        return row[dependents - 1]
    d10, d11 = row[9], row[10]
    return d11 - (d10 - d11) * (dependents - 11)


def _child_credit(children: int) -> int:
    """별표2 제3호 — 8세 이상 20세 이하 자녀 수별 공제액."""
    if children <= 0:
        return 0
    if children == 1:
        return 20_830
    if children == 2:
        return 45_830
    return 45_830 + 33_330 * (children - 2)


# 별표2 제6호 — 월급여액 10,000천원 초과 구간.
# (구간 상한(원), 정액 가산액, 초과 기산점(원), 세율, 98% 적용 여부)
_OVER_BRACKETS: tuple[tuple[float, int, int, float, bool], ...] = (
    (14_000_000, 25_000, 10_000_000, 0.35, True),
    (28_000_000, 1_397_000, 14_000_000, 0.38, True),
    (30_000_000, 6_610_600, 28_000_000, 0.40, True),
    (45_000_000, 7_394_600, 30_000_000, 0.40, False),
    (87_000_000, 13_394_600, 45_000_000, 0.42, False),
    (float("inf"), 31_034_600, 87_000_000, 0.45, False),
)


def _over_table_addition(monthly_wage: int) -> float:
    for upper, flat, floor, rate, apply98 in _OVER_BRACKETS:
        if monthly_wage <= upper:
            excess = monthly_wage - floor
            if apply98:
                excess *= 0.98
            return flat + excess * rate
    raise AssertionError("unreachable")  # pragma: no cover


def lookup_wage_tax(monthly_wage: int, dependents: int = 1, children: int = 0) -> int:
    """월급여액(비과세·학자금 제외, 원)에 대한 간이세액표상 소득세.

    ``children`` 은 공제대상가족 중 8세 이상 20세 이하 자녀 수로, 기본값은 0이다.
    거래처가 자녀 자료를 제출하지 않으면 자녀가 없는 것으로 보고 세액을 계산한다
    (자녀 공제는 세액을 줄이므로, 0으로 두면 과소징수가 아닌 쪽으로 안전하다).
    """
    if monthly_wage <= 0:
        return 0
    dependents = max(1, dependents)

    if monthly_wage > _TABLE_MAX_WAGE:
        anchor = _row_for(_TABLE_MAX_WAGE)
        assert anchor is not None
        # 10원 미만은 원천징수 관행대로 절사한다.
        tax = _tax_for_dependents(anchor, dependents)
        tax += int(_over_table_addition(monthly_wage) // 10) * 10
    else:
        row = _row_for(monthly_wage)
        if row is None:  # 표 최저 구간(770천원) 미만은 세액 없음
            return 0
        tax = _tax_for_dependents(row, dependents)

    return max(0, tax - _child_credit(children))
