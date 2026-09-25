"""거래처 급여지급일 설정 → 위하고 급여자료입력 지급일."""

from datetime import date

from app.services.payroll_defaults import resolve_pay_date


def test_next_month_pay_day():
    assert resolve_pay_date("2026-06", 1, 25) == date(2026, 7, 25)


def test_same_month_and_year_rollover():
    assert resolve_pay_date("2026-06", 0, 10) == date(2026, 6, 10)
    assert resolve_pay_date("2026-12", 1, 10) == date(2027, 1, 10)


def test_day_past_month_end_is_last_day():
    assert resolve_pay_date("2026-01", 1, 31) == date(2026, 2, 28)
    assert resolve_pay_date("2028-01", 1, 30) == date(2028, 2, 29)


def test_unset_returns_none():
    assert resolve_pay_date("2026-06", None, 25) is None
    assert resolve_pay_date("2026-06", 1, None) is None
