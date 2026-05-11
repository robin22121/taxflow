"""Authenticated collection endpoint — used by the dashboard 'manual paste' UI
and by webhook handlers (kakao/email) after they resolve a tenant.

The full pipeline:
    raw text → AI parser → matching engine → upserts PayrollEntry + (optionally) follow-up.
"""

from __future__ import annotations

from datetime import UTC, datetime as _dt

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
from app.services.tax_calc import calculate_withholding_tax, income_type_to_a_code

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


async def _persist_results(
    db: AsyncSession,
    session: CollectionSession,
    client: Client,
    filing: MonthlyFiling,
    matching: MatchingResult,
    employees: list[Employee],
    text: str,
    channel: str,
) -> CollectMessageOut:
    """Save collection event and payroll entries to DB."""
    # Record event
    db.add(
        CollectionEvent(
            session_id=session.id,
            event_type=f"RECEIVE_{channel.upper()}",
            channel=channel,
            raw_text=text,
            raw_payload={
                "matched": len(matching.entries),
                "new_hire": len(matching.new_hire_followups),
                "resignation": len(matching.resignation_followups),
                "ambiguous": len(matching.ambiguous_followups),
            },
        )
    )

    # Replace existing entries (never delete approved ones)
    existing = (
        await db.execute(
            select(PayrollEntry).where(PayrollEntry.collection_session_id == session.id)
        )
    ).scalars().all()
    if any(e.approved for e in existing):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "이미 승인된 엔트리가 있습니다. 승인을 취소한 후 재수집하세요.",
        )
    for e in existing:
        await db.delete(e)
    await db.flush()

    # Create new entries
    emp_by_id = {e.id: e for e in employees}
    needs_followup_count = 0

    for cand in matching.entries:
        taxable = cand.total_amount - cand.non_taxable
        matched_emp = emp_by_id.get(cand.employee_id) if cand.employee_id else None
        biz_code = matched_emp.business_type_code if matched_emp and cand.income_type == IncomeType.BUSINESS else None
        tax = calculate_withholding_tax(
            cand.income_type, taxable, dependents=1, business_type_code=biz_code,
        )
        a_code = income_type_to_a_code(cand.income_type, is_corporation=client.is_corporation)
        salary_amt = cand.total_amount if cand.income_type == IncomeType.WAGE else None
        bonus_amt = 0 if cand.income_type == IncomeType.WAGE else None

        entry = PayrollEntry(
            monthly_filing_id=filing.id,
            collection_session_id=session.id,
            client_id=client.id,
            employee_id=cand.employee_id,
            raw_name=cand.raw_name,
            income_type=cand.income_type,
            a_code=a_code,
            business_type_code=biz_code,
            total_amount=cand.total_amount,
            salary_amount=salary_amt,
            bonus_amount=bonus_amt,
            non_taxable=cand.non_taxable,
            taxable=taxable,
            income_tax=tax.income_tax,
            local_tax=tax.local_tax,
            match_status=cand.match_status,
            prev_amount=cand.prev_amount,
            anomaly_notes=cand.anomaly_notes or None,
        )
        if cand.needs_followup:
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
) -> CollectMessageOut:
    employees, prev_entries = await _build_context(db, client, filing)
    matching = await _parse_and_match(text, client, filing, employees, prev_entries)
    return await _persist_results(db, session, client, filing, matching, employees, text, channel)


def _prev_period(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


# Exposed so public router can reuse the pipeline
__all__ = ["_ingest_message", "router"]
