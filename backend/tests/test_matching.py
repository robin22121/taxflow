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


def test_new_hire_suspected_hints_existing_employee_by_name():
    """AI가 이름만 보고 신규로 분류해도, 마스터에 같은 이름이 있으면 힌트를 붙인다
    (2026-10-02 — 이미 등록된 직원이 매번 신규로 오인식되는 문제 제보)."""
    parsed = PayrollParsingResult(
        new_hire_suspected=[
            NewHireSuspected(name="김연호", amount=1_000_000, income_type="WAGE"),
        ]
    )
    res = reconcile(
        parsed,
        master=_master([("e1", "김연호")]),
        previous_month={},
    )
    assert res.entries[0].match_status == MatchStatus.NEW_HIRE_SUSPECTED
    assert res.entries[0].employee_id is None  # 자동 연결은 하지 않는다
    assert res.entries[0].possible_match_employee_id == "e1"
    assert res.entries[0].possible_match_employee_name == "김연호"


def test_new_hire_suspected_no_hint_when_no_name_match():
    """정말 신규면 힌트가 안 붙는다."""
    parsed = PayrollParsingResult(
        new_hire_suspected=[
            NewHireSuspected(name="박신입", amount=1_000_000, income_type="WAGE"),
        ]
    )
    res = reconcile(
        parsed,
        master=_master([("e1", "김연호")]),
        previous_month={},
    )
    assert res.entries[0].possible_match_employee_id is None


def test_new_hire_suspected_hint_excludes_already_matched_this_round():
    """이번 라운드에 이미 매칭된 id는 같은 이름이라도 힌트 후보에서 뺀다
    (같은 소득구분의 두 번째 신규는 다른 경고가 필요하다는 신호)."""
    parsed = PayrollParsingResult(
        matched_employees=[
            MatchedEmployee(name="김연호", employee_id="e1", amount=1_000_000),
        ],
        new_hire_suspected=[
            NewHireSuspected(name="김연호", amount=500_000, income_type="BUSINESS"),
        ],
    )
    res = reconcile(
        parsed,
        master=_master([("e1", "김연호")]),  # 근로소득 행 하나뿐 — 사업소득 행 없음
        previous_month={"e1": 1_000_000},
    )
    new_hire_entry = next(e for e in res.entries if e.match_status == MatchStatus.NEW_HIRE_SUSPECTED)
    assert new_hire_entry.possible_match_employee_id is None


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
