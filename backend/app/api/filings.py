"""Monthly filing endpoints — create, request collection, dashboard, excel download."""

from datetime import UTC, datetime as _dt

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
from app.services.invite import (
    get_or_create_session as _get_or_create_session,
    send_invite_to_client,
)
from app.services.simple_statement_excel import (
    generate_business_statement,
    generate_wage_statement,
)
from app.services.payroll_excel import generate_payroll_excel
from app.services.wehago_excel import generate_wehago_excel

router = APIRouter()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _session_out(session: CollectionSession, client: Client) -> CollectionSessionOut:
    return CollectionSessionOut(
        id=session.id,
        client_id=client.id,
        client_name=client.business_name,
        status=session.status.value,
        request_token=session.request_token,
        has_responses=False,
        has_anomalies=False,
        entry_count=0,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


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
        session = await _get_or_create_session(db, filing, client, ttl_days=14)

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
        out.append(_session_out(session, client))

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

    patch = payload.model_dump(exclude_unset=True)
    for field_name, value in patch.items():
        if field_name == "income_type" and value is not None:
            from app.models.payroll import IncomeType
            entry.income_type = IncomeType(value)
            continue
        setattr(entry, field_name, value)

    # If 비과세 세분이 patch되면 non_taxable을 합으로 재계산
    breakdown_changed = any(k in patch for k in ("meal_amount", "car_amount", "childcare_amount"))
    if breakdown_changed and "non_taxable" not in patch:
        entry.non_taxable = (entry.meal_amount or 0) + (entry.car_amount or 0) + (entry.childcare_amount or 0)

    # Auto-recompute taxes / 4대보험 only if money fields changed AND
    # user did not manually set the corresponding values in the same PATCH.
    money_changed = any(
        k in patch for k in ("total_amount", "non_taxable", "income_type",
                             "meal_amount", "car_amount", "childcare_amount")
    )
    if money_changed:
        entry.taxable = entry.total_amount - entry.non_taxable
        manual_tax = "income_tax" in patch or "local_tax" in patch
        if not manual_tax:
            from app.services.tax_calc import calculate_withholding_tax
            tax = calculate_withholding_tax(
                entry.income_type, entry.taxable, dependents=entry.dependents or 1
            )
            entry.income_tax = tax.income_tax
            entry.local_tax = tax.local_tax
        manual_si = any(k in patch for k in (
            "national_pension", "health_insurance", "employment_insurance", "longterm_care"
        ))
        if not manual_si:
            from app.services.tax_calc import calculate_social_insurance
            si = calculate_social_insurance(entry.taxable, entry.income_type)
            entry.national_pension = si.national_pension
            entry.health_insurance = si.health_insurance
            entry.employment_insurance = si.employment_insurance
            entry.longterm_care = si.longterm_care

    await db.commit()
    await db.refresh(entry)
    return entry


@router.delete("/{filing_id}/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(
    filing_id: str,
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    entry = await db.get(PayrollEntry, entry_id)
    if not entry or entry.monthly_filing_id != filing_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    filing = await db.get(MonthlyFiling, filing_id)
    if filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    await db.delete(entry)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


@router.get("/{filing_id}/payroll-excel")
async def download_payroll_excel(
    filing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """급여대장 엑셀 다운로드."""
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

    client = await db.get(Client, entries[0].client_id)
    client_name = client.business_name if client else ""

    blob = generate_payroll_excel(list(entries), period=filing.period, client_name=client_name)
    from urllib.parse import quote
    korean_name = f"{client_name or '급여대장'}-{filing.period}.xlsx"
    ascii_fallback = f"payroll_{filing.period}.xlsx"
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            # RFC 5987: ASCII fallback + UTF-8 percent-encoded for non-Latin-1
            "Content-Disposition": (
                f'attachment; filename="{ascii_fallback}"; '
                f"filename*=UTF-8''{quote(korean_name)}"
            ),
        },
    )


@router.get("/{filing_id}/statement-wage")
async def download_wage_statement(
    filing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """간이지급명세서(근로소득) 엑셀 다운로드."""
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    entries = list(
        (
            await db.execute(
                select(PayrollEntry)
                .where(
                    PayrollEntry.monthly_filing_id == filing_id,
                    PayrollEntry.income_type == "WAGE",
                    PayrollEntry.employee_id.isnot(None),
                )
                .options(selectinload(PayrollEntry.employee))
            )
        ).scalars().all()
    )
    if not entries:
        raise HTTPException(status.HTTP_409_CONFLICT, "근로소득 항목이 없습니다.")

    blob = generate_wage_statement(entries, period=filing.period)
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="statement_wage_{filing.period}.xlsx"',
        },
    )


@router.get("/{filing_id}/statement-business")
async def download_business_statement(
    filing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """간이지급명세서(사업소득) 엑셀 다운로드."""
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    entries = list(
        (
            await db.execute(
                select(PayrollEntry)
                .where(
                    PayrollEntry.monthly_filing_id == filing_id,
                    PayrollEntry.income_type == "BUSINESS",
                    PayrollEntry.employee_id.isnot(None),
                )
                .options(selectinload(PayrollEntry.employee))
            )
        ).scalars().all()
    )
    if not entries:
        raise HTTPException(status.HTTP_409_CONFLICT, "사업소득 항목이 없습니다.")

    blob = generate_business_statement(entries, period=filing.period)
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="statement_business_{filing.period}.xlsx"',
        },
    )


@router.post("/{filing_id}/invite", response_model=list[CollectionSessionOut])
async def send_invite(
    filing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CollectionSessionOut]:
    """거래처에 초대장 발송 — 알림톡 + 이메일로 전용 수신 주소 안내.

    기존 request_collection과 달리, 거래처에 전용 이메일 주소(collect+xxx@taxflow.ai)를
    안내하고, 카카오톡/URL 입력폼 링크도 함께 제공.
    """
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    # 세무사사무소 이름 조회
    from app.models import TaxOffice
    office = await db.get(TaxOffice, user.tax_office_id)
    office_name = office.name if office else "세무사사무소"

    clients = (
        await db.execute(
            select(Client).where(Client.tax_office_id == user.tax_office_id)
        )
    ).scalars().all()

    out: list[CollectionSessionOut] = []
    for client in clients:
        session, _ = await send_invite_to_client(db, filing, client, office_name)
        out.append(_session_out(session, client))

    filing.status = MonthlyFilingStatus.COLLECTING
    filing.total_clients = len(out)
    await db.commit()
    return out
