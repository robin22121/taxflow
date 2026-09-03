"""미리보기 행 변환 — 증감 표현("50만원 감액")과 기존 항목 수정 처리."""

from __future__ import annotations

from app.api.collect import _entry_key, _preview_row
from app.models.payroll import IncomeType, MatchStatus, PayrollEntry
from app.services.matching import PayrollEntryCandidate


def _cand(amount: int, *, name: str = "장수민", employee_id: str | None = "e1") -> PayrollEntryCandidate:
    return PayrollEntryCandidate(
        raw_name=name,
        employee_id=employee_id,
        income_type=IncomeType.WAGE,
        total_amount=amount,
        non_taxable=0,
        match_status=MatchStatus.MATCHED,
    )


def _existing(amount: int, *, entry_id: str = "p1") -> PayrollEntry:
    entry = PayrollEntry(
        raw_name="장수민",
        employee_id="e1",
        income_type=IncomeType.WAGE,
        total_amount=amount,
    )
    entry.id = entry_id
    return entry


def test_negative_amount_applies_as_decrease_to_existing_entry():
    row = _preview_row(_cand(-500_000), "장수민", _existing(3_000_000))
    assert row.mode == "update"
    assert row.entry_id == "p1"
    assert row.existing_amount == 3_000_000
    assert row.total_amount == 2_500_000


def test_positive_amount_replaces_existing_entry():
    row = _preview_row(_cand(2_800_000), "장수민", _existing(3_000_000))
    assert row.mode == "update"
    assert row.total_amount == 2_800_000


def test_new_employee_is_created():
    row = _preview_row(_cand(2_000_000, name="박지훈", employee_id=None), None, None)
    assert row.mode == "create"
    assert row.entry_id is None
    assert row.total_amount == 2_000_000


def test_negative_amount_without_existing_entry_is_clamped_and_flagged():
    """기존 항목 없이 증감만 오면 금액을 확정할 수 없다 — 0으로 두고 확인 대상."""
    row = _preview_row(_cand(-2_000_000), "장수민", None)
    assert row.total_amount == 0
    assert row.needs_followup is True


def test_decrease_below_zero_is_clamped():
    row = _preview_row(_cand(-5_000_000), "장수민", _existing(3_000_000))
    assert row.total_amount == 0


def test_entry_key_falls_back_to_name():
    assert _entry_key("e1", "장수민") == "e1"
    assert _entry_key(None, "장수민") == "__name:장수민"
