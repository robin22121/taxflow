"""Authenticated collection endpoint — used by the dashboard 'manual paste' UI
and by webhook handlers (kakao/email) after they resolve a tenant.

The full pipeline:
    raw text → AI parser → matching engine → upserts PayrollEntry + (optionally) follow-up.
"""

from __future__ import annotations

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
from app.services.matching import EmployeeMaster, reconcile
from app.services.tax_calc import calculate_withholding_tax

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


async def _ingest_message(
    *,
    db: AsyncSession,
    session: CollectionSession,
    client: Client,
    filing: MonthlyFiling,
    text: str,
    channel: str,
) -> CollectMessageOut:
    # 1. Build context for the AI: employee master + previous month
    employees = (
        await db.execute(
            select(Employee)
            .where(Employee.client_id == client.id, Employee.status != EmploymentStatus.RESIGNED)
        )
    ).scalars().all()

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

    employee_master_payload = [
        {
            "id": e.id,
            "name": e.name,
            "last_amount": next(
                (p.total_amount for p in prev_entries if p.employee_id == e.id), None
            ),
        }
        for e in employees
    ]
    previous_month_payload = [
        {"name": p.raw_name, "employee_id": p.employee_id, "amount": p.total_amount}
        for p in prev_entries
        if p.employee_id
    ]

    # 2. Run AI parser
    parsed = await parse_payroll_message(
        raw_text=text,
        client_name=client.business_name,
        employee_master=employee_master_payload,
        previous_month_data=previous_month_payload,
        period=filing.period,
    )

    # 3. Run matching engine
    masters = [
        EmployeeMaster(
            id=e.id,
            name=e.name,
            last_amount=next((p.total_amount for p in prev_entries if p.employee_id == e.id), None),
            employee_code=e.employee_code,
        )
        for e in employees
    ]
    prev_amounts = {p.employee_id: p.total_amount for p in prev_entries if p.employee_id}
    matching = reconcile(parsed, masters, prev_amounts)

    # 4. Persist event + upsert PayrollEntry rows for this session
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

    # Replace existing entries for this session (idempotent re-ingest)
    existing = (
        await db.execute(
            select(PayrollEntry).where(PayrollEntry.collection_session_id == session.id)
        )
    ).scalars().all()
    for e in existing:
        await db.delete(e)
    await db.flush()

    needs_followup_count = 0
    for cand in matching.entries:
        taxable = cand.total_amount - cand.non_taxable
        tax = calculate_withholding_tax(cand.income_type, taxable, dependents=1)
        entry = PayrollEntry(
            monthly_filing_id=filing.id,
            collection_session_id=session.id,
            client_id=client.id,
            employee_id=cand.employee_id,
            raw_name=cand.raw_name,
            income_type=cand.income_type,
            total_amount=cand.total_amount,
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
    from datetime import UTC, datetime as _dt
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


def _prev_period(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


# Exposed so public router can reuse the pipeline
__all__ = ["_ingest_message", "router"]
