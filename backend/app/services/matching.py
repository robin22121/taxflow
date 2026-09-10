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
_ABNORMAL_HIGH_KRW = 100_000_000  # 1억 이상이면 비정상 금액 플래그
_ABNORMAL_LOW_KRW = 10_000  # 1만원 이하이면 비정상 금액 플래그


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
    # ``None`` = 원시자료에 항목 없음(거래처 기본값·자체 계산으로 채움),
    # ``0`` = 원시자료가 0원이라고 명시함(그대로 0).
    non_taxable: int | None = None
    meal_amount: int | None = None
    car_amount: int | None = None
    childcare_amount: int | None = None
    # 회사가 이미 적용한 4대보험 실제 공제액. 있으면 재계산하지 않고 그대로 쓴다.
    national_pension: int | None = None
    health_insurance: int | None = None
    employment_insurance: int | None = None
    longterm_care: int | None = None
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
    unconfirmed_followups: list[dict[str, Any]] = field(default_factory=list)


_SOURCE_PAY_ITEM_FIELDS = (
    "non_taxable", "meal_amount", "car_amount", "childcare_amount",
    "national_pension", "health_insurance", "employment_insurance", "longterm_care",
)


def _source_pay_items(parsed_item: Any) -> dict[str, int | None]:
    """AI가 원시자료에서 읽은 지급·공제 항목을 그대로 옮긴다.

    키가 없으면 ``None`` — 원시자료에 항목이 없었다는 뜻이므로, 뒤에서 거래처
    기본값이나 자체 계산으로 채운다. ``0`` 은 "0원이라고 적혀 있음"이라 유지된다.
    """
    return {f: getattr(parsed_item, f, None) for f in _SOURCE_PAY_ITEM_FIELDS}


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
        _flag_abnormal_amount(anomaly, m.amount, m.name)
        entries.append(
            PayrollEntryCandidate(
                raw_name=m.name,
                employee_id=emp_id,
                income_type=_to_income_type(m.income_type),
                total_amount=m.amount,
                **_source_pay_items(m),
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
        nh_anomaly: dict[str, Any] = {}
        _flag_abnormal_amount(nh_anomaly, n.amount, n.name)
        entries.append(
            PayrollEntryCandidate(
                raw_name=n.name,
                employee_id=None,
                income_type=_to_income_type(n.income_type),
                total_amount=n.amount,
                **_source_pay_items(n),
                match_status=MatchStatus.NEW_HIRE_SUSPECTED,
                anomaly_notes=nh_anomaly,
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

    # 4. master members the AI didn't mention → UNCONFIRMED (계속근무/퇴사 확인 필요)
    #    자동 퇴사 처리하지 않음. 거래처에 확인 요청 후 세무사가 판단.
    unconfirmed_followups: list[dict[str, Any]] = []
    unmentioned = [
        e for e in master
        if e.id not in seen_ids
        and e.id not in {f["employee_id"] for f in resignation_followups}
        and previous_month.get(e.id, 0) > 0
    ]
    for emp in unmentioned:
        prev_amt = previous_month[emp.id]
        entries.append(
            PayrollEntryCandidate(
                raw_name=emp.name,
                employee_id=emp.id,
                income_type=IncomeType.WAGE,
                total_amount=0,  # 이번달 급여 미확인 — 전월 금액은 prev_amount에만
                non_taxable=0,
                match_status=MatchStatus.UNCONFIRMED,
                prev_amount=prev_amt,
                anomaly_notes={"unconfirmed": {
                    "reason": "이번달 자료에 누락 — 계속근무 여부 확인 필요",
                    "prev_amount": prev_amt,
                }},
                needs_followup=True,
                followup_reason="unconfirmed_status",
            )
        )
        unconfirmed_followups.append({
            "employee_id": emp.id,
            "name": emp.name,
            "prev_amount": prev_amt,
        })

    # 5. ambiguous items — pass through for human review
    ambiguous_followups = [
        {"raw_text": a.raw_text, "issue": a.issue} for a in parsed.ambiguous_items
    ]

    return MatchingResult(
        entries=entries,
        new_hire_followups=new_hire_followups,
        resignation_followups=resignation_followups,
        ambiguous_followups=ambiguous_followups,
        unconfirmed_followups=unconfirmed_followups,
    )


def _flag_abnormal_amount(anomaly: dict[str, Any], amount: int, name: str) -> None:
    """비정상 금액 플래그 — 세무사에게 확인 요청."""
    if amount >= _ABNORMAL_HIGH_KRW:
        anomaly["abnormal_amount"] = {
            "amount": amount,
            "reason": f"금액 비정상 (₩{amount:,} — 1억 이상)",
        }
    elif 0 < amount <= _ABNORMAL_LOW_KRW:
        anomaly["abnormal_amount"] = {
            "amount": amount,
            "reason": f"금액 비정상 (₩{amount:,} — 1만원 이하)",
        }
    elif amount == 0:
        anomaly["abnormal_amount"] = {
            "amount": 0,
            "reason": "금액 0원",
        }


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
