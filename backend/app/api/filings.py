"""Monthly filing endpoints — create, request collection, dashboard, excel download."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.channels import MessageRecipient, get_alimtalk_channel
from app.config import get_settings
from app.core.deps import get_current_user, get_db
from app.models import (
    Client,
    CollectionEvent,
    CollectionSession,
    CollectionSessionStatus,
    Employee,
    MonthlyFiling,
    MonthlyFilingStatus,
    PayrollEntry,
    User,
)
from app.schemas.filings import (
    CollectionSessionOut,
    FilingDashboard,
    MonthlyFilingCreate,
    MonthlyFilingOut,
    PayrollEntryOut,
    PayrollEntryUpdate,
)
from app.services.secure_tokens import issue_token, public_url
from app.services.wehago_excel import generate_wehago_excel

router = APIRouter()


@router.post("", response_model=MonthlyFilingOut, status_code=status.HTTP_201_CREATED)
async def create_filing(
    payload: MonthlyFilingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MonthlyFiling:
    existing = (
        await db.execute(
            select(MonthlyFiling).where(
                MonthlyFiling.tax_office_id == user.tax_office_id,
                MonthlyFiling.period == payload.period,
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    filing = MonthlyFiling(tax_office_id=user.tax_office_id, period=payload.period)
    db.add(filing)
    await db.commit()
    await db.refresh(filing)
    return filing


@router.get("", response_model=list[MonthlyFilingOut])
async def list_filings(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MonthlyFiling]:
    rows = (
        await db.execute(
            select(MonthlyFiling)
            .where(MonthlyFiling.tax_office_id == user.tax_office_id)
            .order_by(MonthlyFiling.period.desc())
        )
    ).scalars().all()
    return list(rows)


@router.post("/{filing_id}/request", response_model=list[CollectionSessionOut])
async def request_collection(
    filing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CollectionSessionOut]:
    """Create a CollectionSession per client + send alimtalk."""
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    clients = (
        await db.execute(
            select(Client).where(Client.tax_office_id == user.tax_office_id)
        )
    ).scalars().all()

    channel = get_alimtalk_channel()
    settings = get_settings()
    out: list[CollectionSessionOut] = []

    for client in clients:
        # Avoid duplicate sessions
        existing = (
            await db.execute(
                select(CollectionSession).where(
                    CollectionSession.monthly_filing_id == filing.id,
                    CollectionSession.client_id == client.id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            session = existing
        else:
            token = await issue_token(
                db,
                client_id=client.id,
                purpose="COLLECTION_REQUEST",
                ttl=timedelta(days=14),
                context={"filing_id": filing.id},
            )
            session = CollectionSession(
                monthly_filing_id=filing.id,
                client_id=client.id,
                request_token=token.token,
            )
            db.add(session)
            await db.flush()
            # Wire token to session
            token.collection_session_id = session.id

        # Send alimtalk
        url = f"{settings.app_public_url}/r/{session.request_token}"
        body = (
            f"[{client.business_name}] {filing.period} 원천세 자료 요청드립니다.\n"
            f"아래 링크에서 직원 인건비를 입력하시거나, 평소처럼 이 채팅에 답장해주셔도 됩니다.\n"
            f"🔗 {url}"
        )
        result = await channel.send(
            MessageRecipient(
                name=client.business_name,
                phone=client.contact_phone,
                email=client.contact_email,
            ),
            body=body,
            template_code="COLLECTION_REQUEST",
            url=url,
        )
        session.status = (
            CollectionSessionStatus.SENT if result.accepted else CollectionSessionStatus.PENDING
        )
        if result.accepted:
            from datetime import UTC, datetime as _dt
            session.request_sent_at = _dt.now(UTC)

        db.add(
            CollectionEvent(
                session_id=session.id,
                event_type="SEND_ALIMTALK",
                channel=result.channel,
                raw_text=body,
                raw_payload={"accepted": result.accepted, "msg_id": result.provider_msg_id},
            )
        )

        out.append(
            CollectionSessionOut(
                id=session.id,
                client_id=client.id,
                client_name=client.business_name,
                status=session.status.value,
                request_token=session.request_token,
                has_responses=False,
                has_anomalies=False,
                entry_count=0,
            )
        )

    filing.status = MonthlyFilingStatus.COLLECTING
    filing.total_clients = len(out)
    await db.commit()
    return out


@router.get("/{filing_id}/dashboard", response_model=FilingDashboard)
async def get_dashboard(
    filing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FilingDashboard:
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    sessions = (
        await db.execute(
            select(CollectionSession)
            .where(CollectionSession.monthly_filing_id == filing_id)
            .options(selectinload(CollectionSession.client))
        )
    ).scalars().all()

    # entry counts per session
    counts = dict(
        (
            await db.execute(
                select(PayrollEntry.collection_session_id, func.count())
                .where(PayrollEntry.monthly_filing_id == filing_id)
                .group_by(PayrollEntry.collection_session_id)
            )
        ).all()
    )

    # anomaly check: any entry with non-empty anomaly_notes
    anomaly_ids = {
        sid
        for (sid,) in (
            await db.execute(
                select(PayrollEntry.collection_session_id)
                .where(
                    PayrollEntry.monthly_filing_id == filing_id,
                    PayrollEntry.anomaly_notes.isnot(None),
                )
                .distinct()
            )
        ).all()
    }

    out_sessions = [
        CollectionSessionOut(
            id=s.id,
            client_id=s.client_id,
            client_name=s.client.business_name,
            status=s.status.value,
            request_token=s.request_token,
            has_responses=counts.get(s.id, 0) > 0,
            has_anomalies=s.id in anomaly_ids,
            entry_count=counts.get(s.id, 0),
        )
        for s in sessions
    ]

    return FilingDashboard(
        filing=MonthlyFilingOut.model_validate(filing),
        sessions=out_sessions,
    )


@router.get("/{filing_id}/entries", response_model=list[PayrollEntryOut])
async def list_entries(
    filing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PayrollEntry]:
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")
    rows = (
        await db.execute(
            select(PayrollEntry).where(PayrollEntry.monthly_filing_id == filing_id)
        )
    ).scalars().all()
    return list(rows)


@router.patch("/{filing_id}/entries/{entry_id}", response_model=PayrollEntryOut)
async def update_entry(
    filing_id: str,
    entry_id: str,
    payload: PayrollEntryUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PayrollEntry:
    entry = await db.get(PayrollEntry, entry_id)
    if not entry or entry.monthly_filing_id != filing_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    filing = await db.get(MonthlyFiling, filing_id)
    if filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN)

    for field_name, value in payload.model_dump(exclude_unset=True).items():
        if field_name == "income_type" and value is not None:
            from app.models.payroll import IncomeType
            entry.income_type = IncomeType(value)
            continue
        setattr(entry, field_name, value)

    # Recompute taxes if money fields changed
    if any(k in payload.model_dump(exclude_unset=True) for k in ("total_amount", "non_taxable", "income_type")):
        from app.services.tax_calc import calculate_withholding_tax
        entry.taxable = entry.total_amount - entry.non_taxable
        tax = calculate_withholding_tax(
            entry.income_type, entry.taxable, dependents=entry.dependents or 1
        )
        entry.income_tax = tax.income_tax
        entry.local_tax = tax.local_tax

    await db.commit()
    await db.refresh(entry)
    return entry


@router.get("/{filing_id}/wehago-excel")
async def download_wehago_excel(
    filing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    entries = (
        await db.execute(
            select(PayrollEntry)
            .where(
                PayrollEntry.monthly_filing_id == filing_id,
                PayrollEntry.approved.is_(True),
                PayrollEntry.employee_id.isnot(None),
            )
            .options(selectinload(PayrollEntry.employee))
        )
    ).scalars().all()
    if not entries:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "승인된 엔트리가 없습니다. 먼저 검증·승인을 완료하세요.",
        )

    blob = generate_wehago_excel(list(entries), period=filing.period)
    filing.status = MonthlyFilingStatus.EXCEL_GENERATED
    await db.commit()

    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="wehago_{filing.period}.xlsx"',
        },
    )
