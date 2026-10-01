"""일용근로소득(DAILY) 근로일수(work_days) 기본값·세액 반영 — _computed_fields."""

from __future__ import annotations

from app.api.collect import _computed_fields
from app.models.payroll import IncomeType, MatchStatus
from app.services.matching import PayrollEntryCandidate
from app.services.payroll_defaults import ResolvedPayrollDefaults

_DEFAULTS = ResolvedPayrollDefaults()


def _daily_cand(total_amount: int, *, work_days: int | None = None) -> PayrollEntryCandidate:
    return PayrollEntryCandidate(
        raw_name="권태식",
        employee_id="e1",
        income_type=IncomeType.DAILY,
        total_amount=total_amount,
        work_days=work_days,
        match_status=MatchStatus.MATCHED,
    )


def test_missing_work_days_defaults_to_20_days():
    """AI가 근무일수를 못 찾으면(None) 1일로 간주해 세액이 과대 계산되는 대신 20일을 기본값으로 쓴다."""
    fields, tax, _si = _computed_fields(_daily_cand(1_500_000), None, _DEFAULTS, None)
    assert fields["work_days"] == 20
    # 일급 75,000원 — 일용근로소득 비과세 한도(1일 15만원) 이하라 세액 0
    assert tax.income_tax == 0


def test_explicit_work_days_is_used_as_is():
    """AI가 원시자료에서 근무일수를 찾았으면 그 값을 그대로 쓴다(20으로 덮어쓰지 않음)."""
    fields, tax, _si = _computed_fields(_daily_cand(1_500_000, work_days=10), None, _DEFAULTS, None)
    assert fields["work_days"] == 10
    # 일급 150,000원 — 비과세 한도와 정확히 같아 세액 0
    assert tax.income_tax == 0


def test_wage_entry_has_no_work_days():
    """일용근로소득이 아니면 work_days는 의미가 없으므로 항상 None."""
    cand = PayrollEntryCandidate(
        raw_name="김소라",
        employee_id="e2",
        income_type=IncomeType.WAGE,
        total_amount=3_000_000,
        match_status=MatchStatus.MATCHED,
    )
    fields, _tax, _si = _computed_fields(cand, None, _DEFAULTS, None)
    assert fields["work_days"] is None
