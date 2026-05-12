"""Employee matching + anomaly engine.

Turns ``PayrollParsingResult`` (from the AI) into a finalized list of
``PayrollEntryCandidate`` records ready to upsert into the DB.

Key responsibilities beyond what the AI does:
1. **Validate** AI-returned ``employee_id`` against the actual master (the AI may hallucinate).
2. **Fuzzy rescue** — when the AI's id is invalid, try ``rapidfuzz`` against names.
3. **Catch missing employees** the AI might have overlooked (paid last month but not this month).
4. **Anomaly flags** — large jumps, unusually low amounts, sudden drops.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rapidfuzz import fuzz, process

from app.models.payroll import IncomeType, MatchStatus
from app.services.ai_parser import PayrollParsingResult

# 매칭 임계값 — fuzzy 매칭에서 이 점수 미만이면 모호 처리
_FUZZY_MATCH_THRESHOLD = 85
_LARGE_CHANGE_RATIO = 1.5  # 이전월 대비 50% 이상 변동
_LARGE_CHANGE_FLOOR_KRW = 300_000  # 이 금액 이하 변동은 anomaly로 보지 않음


@dataclass(slots=True)
class EmployeeMaster:
    id: str
    name: str
    last_amount: int | None = None
    last_paid_at: str | None = None
    employee_code: str | None = None


@dataclass(slots=True)
class PayrollEntryCandidate:
    raw_name: str
    employee_id: str | None
    income_type: IncomeType
    total_amount: int
    non_taxable: int
    meal_amount: int = 0
    car_amount: int = 0
    childcare_amount: int = 0
    match_status: MatchStatus = MatchStatus.AMBIGUOUS
    prev_amount: int | None = None
    anomaly_notes: dict[str, Any] = field(default_factory=dict)
    needs_followup: bool = False
    followup_reason: str | None = None


@dataclass(slots=True)
class MatchingResult:
    entries: list[PayrollEntryCandidate]
    new_hire_followups: list[dict[str, Any]]
    resignation_followups: list[dict[str, Any]]
    ambiguous_followups: list[dict[str, Any]]


def reconcile(
    parsed: PayrollParsingResult,
    master: list[EmployeeMaster],
    previous_month: dict[str, int],
) -> MatchingResult:
    """Reconcile AI output against the master and previous month.

    Args:
        parsed: AI parser output.
        master: 거래처의 활성 직원 마스터.
        previous_month: ``{employee_id: amount}`` mapping for last month.
    """
    by_id = {e.id: e for e in master}
    seen_ids: set[str] = set()
    entries: list[PayrollEntryCandidate] = []

    # 1. matched_employees — validate id, fuzzy rescue if needed
    for m in parsed.matched_employees:
        emp_id, status = _validate_or_rescue(m.employee_id, m.name, by_id, master)
        if emp_id:
            seen_ids.add(emp_id)
        prev = previous_month.get(emp_id) if emp_id else None
        anomaly: dict[str, Any] = {}
        if prev is not None and prev > 0:
            ratio = m.amount / prev if prev else 0
            diff = abs(m.amount - prev)
            if (
                diff >= _LARGE_CHANGE_FLOOR_KRW
                and (ratio >= _LARGE_CHANGE_RATIO or ratio <= 1 / _LARGE_CHANGE_RATIO)
            ):
                anomaly["large_change"] = {
                    "prev": prev,
                    "current": m.amount,
                    "ratio": round(ratio, 2),
                }
        entries.append(
            PayrollEntryCandidate(
                raw_name=m.name,
                employee_id=emp_id,
                income_type=_to_income_type(m.income_type),
                total_amount=m.amount,
                non_taxable=m.non_taxable,
                meal_amount=getattr(m, "meal_amount", 0),
                car_amount=getattr(m, "car_amount", 0),
                childcare_amount=getattr(m, "childcare_amount", 0),
                match_status=status,
                prev_amount=prev,
                anomaly_notes=anomaly,
                needs_followup=bool(anomaly),
                followup_reason="amount_change" if anomaly else None,
            )
        )

    # 2. new_hire_suspected — these stay unmatched until 주민번호 등록됨
    new_hire_followups: list[dict[str, Any]] = []
    for n in parsed.new_hire_suspected:
        entries.append(
            PayrollEntryCandidate(
                raw_name=n.name,
                employee_id=None,
                income_type=_to_income_type(n.income_type),
                total_amount=n.amount,
                non_taxable=n.non_taxable,
                meal_amount=getattr(n, "meal_amount", 0),
                car_amount=getattr(n, "car_amount", 0),
                childcare_amount=getattr(n, "childcare_amount", 0),
                match_status=MatchStatus.NEW_HIRE_SUSPECTED,
                needs_followup=True,
                followup_reason="new_hire_rrn",
            )
        )
        new_hire_followups.append({"name": n.name, "amount": n.amount})

    # 3. resignation_suspected — combine AI suggestions and "unmentioned in master"
    resignation_followups: list[dict[str, Any]] = []
    for r in parsed.resignation_suspected:
        emp = by_id.get(r.employee_id)
        if emp:
            seen_ids.add(emp.id)  # avoid double-counting in the final unmentioned step
        resignation_followups.append(
            {"employee_id": r.employee_id, "name": r.name, "reason": r.reason}
        )

    # 4. master members the AI didn't mention at all → likely resignation/leave
    unmentioned = [
        e for e in master
        if e.id not in seen_ids
        and e.id not in {f["employee_id"] for f in resignation_followups}
        and previous_month.get(e.id, 0) > 0
    ]
    for emp in unmentioned:
        resignation_followups.append(
            {
                "employee_id": emp.id,
                "name": emp.name,
                "reason": "이번달 자료에 누락 (이전월 지급 이력 있음)",
            }
        )

    # 5. ambiguous items — pass through for human review
    ambiguous_followups = [
        {"raw_text": a.raw_text, "issue": a.issue} for a in parsed.ambiguous_items
    ]

    return MatchingResult(
        entries=entries,
        new_hire_followups=new_hire_followups,
        resignation_followups=resignation_followups,
        ambiguous_followups=ambiguous_followups,
    )


def _validate_or_rescue(
    ai_emp_id: str,
    name: str,
    by_id: dict[str, EmployeeMaster],
    master: list[EmployeeMaster],
) -> tuple[str | None, MatchStatus]:
    """If AI-returned id is in master, accept; else fuzzy rescue by name."""
    if ai_emp_id in by_id:
        # confirm name reasonably matches
        emp = by_id[ai_emp_id]
        if fuzz.ratio(emp.name, name) >= 70:
            return emp.id, MatchStatus.MATCHED
        # name mismatch — flag ambiguous
        return ai_emp_id, MatchStatus.AMBIGUOUS

    if not master:
        return None, MatchStatus.AMBIGUOUS

    candidate = process.extractOne(
        name,
        choices={e.id: e.name for e in master},
        scorer=fuzz.ratio,
    )
    if candidate is None:
        return None, MatchStatus.AMBIGUOUS
    matched_name, score, emp_id = candidate
    if score >= _FUZZY_MATCH_THRESHOLD:
        return emp_id, MatchStatus.MATCHED
    return None, MatchStatus.AMBIGUOUS


def _to_income_type(s: str) -> IncomeType:
    try:
        return IncomeType(s)
    except (KeyError, ValueError):
        return IncomeType.WAGE


__all__ = [
    "EmployeeMaster",
    "MatchingResult",
    "PayrollEntryCandidate",
    "reconcile",
]
