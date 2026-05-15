"""Authenticated collection endpoint — used by the dashboard 'manual paste' UI
and by webhook handlers (kakao/email) after they resolve a tenant.

The full pipeline:
    raw text → AI parser → matching engine → upserts PayrollEntry + (optionally) follow-up.
"""

from __future__ import annotations

from datetime import UTC, date, datetime as _dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db
from app.models import (
    Client,
    CollectionEvent,
    CollectionSession,
    CollectionSessionStatus,
    Employee,
    EmploymentStatus,
    MonthlyFiling,
    PayrollEntry,
)
from app.models.payroll import IncomeType, MatchStatus
from app.models import User
from app.schemas.filings import CollectMessageIn, CollectMessageOut
from app.services.ai_parser import parse_payroll_message
from app.services.matching import EmployeeMaster, MatchingResult, reconcile
from app.services.tax_calc import (
    calculate_social_insurance,
    calculate_withholding_tax,
    income_type_to_a_code,
)

router = APIRouter()


@router.post("/sessions/{session_id}/messages", response_model=CollectMessageOut)
async def submit_message(
    session_id: str,
    payload: CollectMessageIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CollectMessageOut:
    session = await db.get(
        CollectionSession,
        session_id,
        options=[selectinload(CollectionSession.client), selectinload(CollectionSession.monthly_filing)],
    )
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if session.monthly_filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    return await _ingest_message(
        db=db,
        session=session,
        client=session.client,
        filing=session.monthly_filing,
        text=payload.text,
        channel=payload.channel,
        sender_name=payload.sender_name,
        received_date=payload.received_date,
    )


# ---------------------------------------------------------------------------
# Pipeline internals
# ---------------------------------------------------------------------------


async def _build_context(
    db: AsyncSession,
    client: Client,
    filing: MonthlyFiling,
) -> tuple[list[Employee], list[PayrollEntry]]:
    """Load employee master and previous month payroll entries."""
    employees = list(
        (
            await db.execute(
                select(Employee)
                .where(Employee.client_id == client.id, Employee.status != EmploymentStatus.RESIGNED)
            )
        ).scalars().all()
    )

    prev_period = _prev_period(filing.period)
    prev_filing = (
        await db.execute(
            select(MonthlyFiling).where(
                MonthlyFiling.tax_office_id == filing.tax_office_id,
                MonthlyFiling.period == prev_period,
            )
        )
    ).scalar_one_or_none()

    prev_entries: list[PayrollEntry] = []
    if prev_filing:
        prev_entries = list(
            (
                await db.execute(
                    select(PayrollEntry).where(
                        PayrollEntry.monthly_filing_id == prev_filing.id,
                        PayrollEntry.client_id == client.id,
                    )
                )
            ).scalars().all()
        )

    return employees, prev_entries


async def _parse_and_match(
    text: str,
    client: Client,
    filing: MonthlyFiling,
    employees: list[Employee],
    prev_entries: list[PayrollEntry],
    images: list[tuple[bytes, str]] | None = None,
) -> MatchingResult:
    """Run AI parsing + matching engine. Pure logic, no DB writes."""
    # Build prev_amounts lookup (O(1) per employee instead of O(n))
    prev_by_emp = {p.employee_id: p.total_amount for p in prev_entries if p.employee_id}

    employee_master_payload = [
        {
            "id": e.id,
            "name": e.name,
            "last_amount": prev_by_emp.get(e.id),
        }
        for e in employees
    ]
    previous_month_payload = [
        {"name": p.raw_name, "employee_id": p.employee_id, "amount": p.total_amount}
        for p in prev_entries
        if p.employee_id
    ]

    parsed = await parse_payroll_message(
        raw_text=text,
        client_name=client.business_name,
        employee_master=employee_master_payload,
        previous_month_data=previous_month_payload,
        period=filing.period,
        images=images,
    )

    masters = [
        EmployeeMaster(
            id=e.id,
            name=e.name,
            last_amount=prev_by_emp.get(e.id),
            employee_code=e.employee_code,
        )
        for e in employees
    ]
    return reconcile(parsed, masters, prev_by_emp)


def _detect_field_anomalies(
    anomaly: dict,
    cand,
    prev: PayrollEntry,
    tax,
    si_np: int, si_hi: int, si_ei: int, si_ltc: int,
) -> None:
    """전월 대비 필드별 이상치를 anomaly_notes에 기록."""
    fields: dict[str, tuple[int, int]] = {}
    # 총액 변동은 기존 large_change로 이미 처리됨
    # 4대보험 변동 감지 (전월과 다르면 기록)
    if prev.national_pension > 0 and abs(si_np - prev.national_pension) > 1000:
        fields["national_pension"] = (prev.national_pension, si_np)
    if prev.health_insurance > 0 and abs(si_hi - prev.health_insurance) > 1000:
        fields["health_insurance"] = (prev.health_insurance, si_hi)
    # 소득세 변동 (20% 이상이면 기록)
    if prev.income_tax and prev.income_tax > 0:
        tax_change = abs(tax.income_tax - prev.income_tax) / prev.income_tax
        if tax_change > 0.2:
            fields["income_tax"] = (prev.income_tax, tax.income_tax)
    if fields:
        anomaly["field_changes"] = {
            k: {"prev": v[0], "curr": v[1]} for k, v in fields.items()
        }


async def _persist_results(
    db: AsyncSession,
    session: CollectionSession,
    client: Client,
    filing: MonthlyFiling,
    matching: MatchingResult,
    employees: list[Employee],
    text: str,
    channel: str,
    attachments: list[dict] | None = None,
    sender_name: str | None = None,
    received_date: "date | None" = None,
    prev_entries: list[PayrollEntry] | None = None,
) -> CollectMessageOut:
    """Save collection event and payroll entries to DB."""
    payload: dict = {
        "matched": len(matching.entries),
        "new_hire": len(matching.new_hire_followups),
        "resignation": len(matching.resignation_followups),
        "ambiguous": len(matching.ambiguous_followups),
    }
    if attachments:
        # 세무사 대시보드에서 AI 결과와 원본을 대조할 수 있도록 첨부 메타 보존
        payload["attachments"] = attachments

    # Record event — flush immediately to get ID for entry linking
    event = CollectionEvent(
        session_id=session.id,
        event_type=f"RECEIVE_{channel.upper()}",
        channel=channel,
        raw_text=text,
        raw_payload=payload,
        sender_name=sender_name,
        received_date=received_date,
    )
    db.add(event)
    await db.flush()

    # Deduplicate: skip if same filing + same employee already exists (across ALL sessions)
    # 같은 filing 내 다른 세션에서 이미 처리된 직원도 중복 방지
    existing_entries = list(
        (
            await db.execute(
                select(PayrollEntry).where(
                    PayrollEntry.monthly_filing_id == filing.id,
                    PayrollEntry.client_id == client.id,
                )
            )
        ).scalars().all()
    )
    existing_keys: set[str] = set()
    for ex in existing_entries:
        key = ex.employee_id if ex.employee_id else f"__name:{ex.raw_name}"
        existing_keys.add(key)

    emp_by_id = {e.id: e for e in employees}
    # 전월 엔트리 lookup (employee_id 기준)
    prev_by_emp: dict[str, PayrollEntry] = {}
    if prev_entries:
        for pe in prev_entries:
            if pe.employee_id:
                prev_by_emp[pe.employee_id] = pe
    needs_followup_count = 0

    for cand in matching.entries:
        dedup_key = cand.employee_id if cand.employee_id else f"__name:{cand.raw_name}"
        if dedup_key in existing_keys:
            continue

        matched_emp = emp_by_id.get(cand.employee_id) if cand.employee_id else None
        biz_code = matched_emp.business_type_code if matched_emp and cand.income_type == IncomeType.BUSINESS else None
        a_code = income_type_to_a_code(cand.income_type, is_corporation=client.is_corporation)

        # 전월 데이터에서 세부 항목 상속
        prev = prev_by_emp.get(cand.employee_id) if cand.employee_id else None

        # AI가 세부 항목을 추출했는지 확인
        ai_has_breakdown = (cand.meal_amount > 0 or cand.car_amount > 0 or cand.childcare_amount > 0)

        if prev and not ai_has_breakdown:
            # 전월 데이터 기반: 비과세 항목 복사, 기본급만 총액 차이로 조정
            meal = prev.meal_amount
            car = prev.car_amount
            childcare = prev.childcare_amount
            bonus = prev.bonus_amount or 0
            non_taxable_items = meal + car + childcare
            base_salary = cand.total_amount - bonus - non_taxable_items
            if base_salary < 0:
                base_salary = cand.total_amount
                bonus = 0
            non_taxable = non_taxable_items
            salary_amt = base_salary + bonus + non_taxable_items if cand.income_type == IncomeType.WAGE else None
            bonus_amt = bonus if cand.income_type == IncomeType.WAGE else None
        else:
            # AI 추출값 또는 기본값
            meal = cand.meal_amount
            car = cand.car_amount
            childcare = cand.childcare_amount
            breakdown_sum = meal + car + childcare
            non_taxable = max(cand.non_taxable, breakdown_sum)
            salary_amt = cand.total_amount if cand.income_type == IncomeType.WAGE else None
            bonus_amt = 0 if cand.income_type == IncomeType.WAGE else None

        taxable = cand.total_amount - non_taxable
        tax = calculate_withholding_tax(
            cand.income_type, taxable, dependents=1, business_type_code=biz_code,
        )

        # 4대보험: 전월 데이터가 있으면 복사 (월별 변동 거의 없음), 없으면 계산
        if prev and prev.national_pension > 0:
            si_np = prev.national_pension
            si_hi = prev.health_insurance
            si_ei = prev.employment_insurance
            si_ltc = prev.longterm_care
        else:
            si = calculate_social_insurance(taxable, cand.income_type)
            si_np = si.national_pension
            si_hi = si.health_insurance
            si_ei = si.employment_insurance
            si_ltc = si.longterm_care

        # 필드별 이상치 감지
        anomaly = dict(cand.anomaly_notes) if cand.anomaly_notes else {}
        if prev:
            _detect_field_anomalies(anomaly, cand, prev, tax, si_np, si_hi, si_ei, si_ltc)

        entry = PayrollEntry(
            monthly_filing_id=filing.id,
            collection_session_id=session.id,
            collection_event_id=event.id,
            client_id=client.id,
            employee_id=cand.employee_id,
            raw_name=cand.raw_name,
            income_type=cand.income_type,
            a_code=a_code,
            business_type_code=biz_code,
            total_amount=cand.total_amount,
            salary_amount=salary_amt,
            bonus_amount=bonus_amt,
            non_taxable=non_taxable,
            meal_amount=meal,
            car_amount=car,
            childcare_amount=childcare,
            taxable=taxable,
            national_pension=si_np,
            health_insurance=si_hi,
            employment_insurance=si_ei,
            longterm_care=si_ltc,
            income_tax=tax.income_tax,
            local_tax=tax.local_tax,
            match_status=cand.match_status,
            prev_amount=cand.prev_amount,
            anomaly_notes=anomaly or None,
        )
        if (
            cand.needs_followup
            and cand.match_status not in (MatchStatus.UNCONFIRMED, MatchStatus.NEW_HIRE_SUSPECTED)
        ):
            needs_followup_count += 1
        db.add(entry)

    # Update session status
    session.status = (
        CollectionSessionStatus.NEEDS_REVIEW
        if (
            matching.new_hire_followups
            or matching.resignation_followups
            or matching.ambiguous_followups
            or needs_followup_count
        )
        else CollectionSessionStatus.RECEIVED
    )
    session.last_response_at = _dt.now(UTC)

    await db.commit()
    return CollectMessageOut(
        session_id=session.id,
        matched=sum(1 for c in matching.entries if c.match_status == MatchStatus.MATCHED),
        new_hire_suspected=len(matching.new_hire_followups),
        resignation_suspected=len(matching.resignation_followups),
        ambiguous=len(matching.ambiguous_followups),
        needs_followup=needs_followup_count,
        unconfirmed=len(matching.unconfirmed_followups),
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def _ingest_message(
    *,
    db: AsyncSession,
    session: CollectionSession,
    client: Client,
    filing: MonthlyFiling,
    text: str,
    channel: str,
    images: list[tuple[bytes, str]] | None = None,
    attachments: list[dict] | None = None,
    sender_name: str | None = None,
    received_date: "date | None" = None,
) -> CollectMessageOut:
    """
    attachments: 원본 파일 메타 [{"filename":..., "storage_key":..., "kind":..., "mime":...}]
                 세무사 대시보드에서 AI 결과와 대조하기 위해 저장.
    """
    # Safety net: 텍스트가 placeholder만 있고 이미지도 없으면 AI 환각 방지를 위해 스킵
    if not images and _is_only_placeholder(text):
        return await _record_unparseable(db, session, text, channel, attachments,
                                         sender_name=sender_name, received_date=received_date)

    employees, prev_entries = await _build_context(db, client, filing)
    matching = await _parse_and_match(text, client, filing, employees, prev_entries, images=images)
    return await _persist_results(
        db, session, client, filing, matching, employees, text, channel, attachments,
        sender_name=sender_name, received_date=received_date,
        prev_entries=prev_entries,
    )


_PLACEHOLDER_MARKERS = (
    "[이미지 업로드",
    "[이미지 첨부",
    "[첨부:",
)


def _is_only_placeholder(text: str) -> bool:
    """본문이 첨부 placeholder 라인만 있고 실제 텍스트가 없는지 확인."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return True
    return all(any(m in ln for m in _PLACEHOLDER_MARKERS) for ln in lines)


async def _record_unparseable(
    db: AsyncSession,
    session: CollectionSession,
    text: str,
    channel: str,
    attachments: list[dict] | None = None,
    sender_name: str | None = None,
    received_date: "date | None" = None,
) -> CollectMessageOut:
    """본문이 비어있거나 placeholder뿐일 때 — AI 호출 없이 세션만 검토 대기로 표시."""
    payload: dict = {"reason": "no parseable content"}
    if attachments:
        payload["attachments"] = attachments
    db.add(
        CollectionEvent(
            session_id=session.id,
            event_type=f"RECEIVE_{channel.upper()}_UNPARSEABLE",
            channel=channel,
            raw_text=text,
            raw_payload=payload,
            sender_name=sender_name,
            received_date=received_date,
        )
    )
    session.status = CollectionSessionStatus.NEEDS_REVIEW
    session.last_response_at = _dt.now(UTC)
    await db.commit()
    return CollectMessageOut(
        session_id=session.id,
        matched=0,
        new_hire_suspected=0,
        resignation_suspected=0,
        ambiguous=0,
        needs_followup=0,
    )


def _prev_period(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


# Exposed so public router can reuse the pipeline
__all__ = ["_ingest_message", "router"]
