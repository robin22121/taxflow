"""Employee matching engine tests."""

from app.models.payroll import IncomeType, MatchStatus
from app.services.ai_parser import (
    AmbiguousItem,
    MatchedEmployee,
    NewHireSuspected,
    PayrollParsingResult,
    ResignationSuspected,
)
from app.services.matching import EmployeeMaster, reconcile


def _master(employees: list[tuple[str, str]]) -> list[EmployeeMaster]:
    return [EmployeeMaster(id=e[0], name=e[1]) for e in employees]


def test_matched_passthrough():
    parsed = PayrollParsingResult(
        matched_employees=[
            MatchedEmployee(name="김연호", employee_id="e1", amount=1_000_000),
        ]
    )
    res = reconcile(
        parsed,
        master=_master([("e1", "김연호")]),
        previous_month={"e1": 1_000_000},
    )
    assert len(res.entries) == 1
    assert res.entries[0].match_status == MatchStatus.MATCHED
    assert res.entries[0].employee_id == "e1"


def test_fuzzy_rescue_with_invalid_id():
    parsed = PayrollParsingResult(
        matched_employees=[
            # AI hallucinated id but name is similar enough
            MatchedEmployee(name="김연호", employee_id="bogus", amount=1_000_000),
        ]
    )
    res = reconcile(
        parsed,
        master=_master([("e1", "김연호")]),
        previous_month={},
    )
    assert res.entries[0].match_status == MatchStatus.MATCHED
    assert res.entries[0].employee_id == "e1"


def test_unmentioned_master_gets_resignation_flag():
    parsed = PayrollParsingResult(
        matched_employees=[
            MatchedEmployee(name="김연호", employee_id="e1", amount=1_000_000),
        ]
    )
    res = reconcile(
        parsed,
        master=_master([("e1", "김연호"), ("e2", "이영수")]),
        previous_month={"e1": 1_000_000, "e2": 1_500_000},
    )
    flagged_ids = {f["employee_id"] for f in res.resignation_followups}
    assert "e2" in flagged_ids


def test_unmentioned_master_no_flag_if_never_paid():
    """Never-paid employees in master shouldn't trigger resignation suspicion."""
    parsed = PayrollParsingResult(
        matched_employees=[
            MatchedEmployee(name="김연호", employee_id="e1", amount=1_000_000),
        ]
    )
    res = reconcile(
        parsed,
        master=_master([("e1", "김연호"), ("e2", "이영수")]),
        previous_month={"e1": 1_000_000},  # e2 has no prior payments
    )
    assert all(f["employee_id"] != "e2" for f in res.resignation_followups)


def test_large_change_flagged_as_anomaly():
    parsed = PayrollParsingResult(
        matched_employees=[
            MatchedEmployee(name="김연호", employee_id="e1", amount=2_500_000),
        ]
    )
    res = reconcile(
        parsed,
        master=_master([("e1", "김연호")]),
        previous_month={"e1": 1_000_000},  # 100 → 250: 2.5x
    )
    e = res.entries[0]
    assert "large_change" in e.anomaly_notes
    assert e.needs_followup
    assert e.followup_reason == "amount_change"


def test_small_change_not_flagged():
    parsed = PayrollParsingResult(
        matched_employees=[
            MatchedEmployee(name="김연호", employee_id="e1", amount=1_050_000),
        ]
    )
    res = reconcile(
        parsed,
        master=_master([("e1", "김연호")]),
        previous_month={"e1": 1_000_000},
    )
    assert res.entries[0].anomaly_notes == {}
    assert not res.entries[0].needs_followup


def test_new_hire_marked_with_followup():
    parsed = PayrollParsingResult(
        new_hire_suspected=[
            NewHireSuspected(name="박민수", amount=1_500_000),
        ]
    )
    res = reconcile(
        parsed,
        master=_master([("e1", "김연호")]),
        previous_month={},
    )
    assert len(res.entries) == 1
    assert res.entries[0].match_status == MatchStatus.NEW_HIRE_SUSPECTED
    assert res.entries[0].employee_id is None
    assert res.entries[0].needs_followup
    assert res.entries[0].followup_reason == "new_hire_rrn"
    assert res.new_hire_followups[0]["name"] == "박민수"


def test_ambiguous_passthrough():
    parsed = PayrollParsingResult(
        ambiguous_items=[AmbiguousItem(raw_text="김씨 100", issue="이름 모호")]
    )
    res = reconcile(parsed, master=_master([]), previous_month={})
    assert res.ambiguous_followups[0]["issue"] == "이름 모호"


def test_explicit_resignation_passes_through_and_dedups():
    parsed = PayrollParsingResult(
        matched_employees=[
            MatchedEmployee(name="김연호", employee_id="e1", amount=1_000_000),
        ],
        resignation_suspected=[
            ResignationSuspected(employee_id="e2", name="이영수", reason="고객이 명시적으로 언급"),
        ],
    )
    res = reconcile(
        parsed,
        master=_master([("e1", "김연호"), ("e2", "이영수")]),
        previous_month={"e1": 1_000_000, "e2": 1_500_000},
    )
    # e2가 두 번 들어가면 안 됨
    e2_followups = [f for f in res.resignation_followups if f["employee_id"] == "e2"]
    assert len(e2_followups) == 1
