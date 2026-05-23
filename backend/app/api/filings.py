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
    InsuranceSummaryOut,
    MonthlyFilingCreate,
    MonthlyFilingOut,
    PayrollEntryOut,
    PayrollEntryUpdate,
)
from app.services.confirmation import send_confirmation
from app.services.invite import (
    get_or_create_session as _get_or_create_session,
    send_invite_to_client,
)
from app.services.insurance_excel import (
    build_insurance_summary,
    generate_acquisition_report,
    generate_combined_insurance_report,
    generate_loss_report,
    generate_remuneration_change_report,
)
from app.services.payslip_excel import generate_payslips
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
    """Create a CollectionSession per client + send alimtalk to ALL clients."""
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    clients = (
        await db.execute(
            select(Client).where(Client.tax_office_id == user.tax_office_id)
        )
    ).scalars().all()

    out: list[CollectionSessionOut] = []
    for client in clients:
        session = await _get_or_create_session(db, filing, client, ttl_days=14)
        await _send_collection_alimtalk(db, session, client, filing)
        out.append(_session_out(session, client))

    filing.status = MonthlyFilingStatus.COLLECTING
    filing.total_clients = len(out)
    await db.commit()
    return out


@router.post("/{filing_id}/sessions/{session_id}/request", response_model=CollectionSessionOut)
async def request_collection_single(
    filing_id: str,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CollectionSessionOut:
    """Send invite (알림톡 → SMS fallback + 이메일) to a single client."""
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    session = await db.get(
        CollectionSession,
        session_id,
        options=[selectinload(CollectionSession.client)],
    )
    if not session or session.monthly_filing_id != filing_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    from app.models import TaxOffice
    office = await db.get(TaxOffice, user.tax_office_id)
    office_name = office.name if office else "세무사사무소"

    await send_invite_to_client(db, filing, session.client, office_name)
    await db.commit()
    return _session_out(session, session.client)


async def _send_collection_alimtalk(
    db: AsyncSession,
    session: CollectionSession,
    client: Client,
    filing: MonthlyFiling,
) -> None:
    """Send a collection request alimtalk for a single client session."""
    channel = get_alimtalk_channel()
    settings = get_settings()

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


@router.post("/{filing_id}/sessions/{session_id}/confirm-with-client")
async def confirm_with_client(
    filing_id: str,
    session_id: str,
    channel: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """AI 인식 결과를 거래처에 같은 채널로 회신해 검증 요청.

    channel: "auto"(기본) | "email" | "kakao" | "sms"
    """
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    session = await db.get(
        CollectionSession,
        session_id,
        options=[selectinload(CollectionSession.client)],
    )
    if not session or session.monthly_filing_id != filing_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    entries = (
        await db.execute(
            select(PayrollEntry)
            .where(PayrollEntry.collection_session_id == session_id)
            .order_by(PayrollEntry.id)
        )
    ).scalars().all()

    from app.models import TaxOffice
    office = await db.get(TaxOffice, user.tax_office_id)
    office_name = office.name if office else "세무사사무소"

    sent, used_channel, error = await send_confirmation(
        db,
        session=session,
        client=session.client,
        filing=filing,
        entries=list(entries),
        office_name=office_name,
        channel=channel or "auto",
    )
    await db.commit()
    return {
        "sent": sent,
        "channel": used_channel,
        "error": error,
        "entry_count": len(entries),
    }


@router.get("/{filing_id}/sessions/{session_id}/attachments")
async def list_session_attachments(
    filing_id: str,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """세션에 누적된 첨부파일 메타 목록 — 세무사가 AI 결과와 대조 검증할 수 있도록."""
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    session = await db.get(CollectionSession, session_id)
    if not session or session.monthly_filing_id != filing_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    events = (
        await db.execute(
            select(CollectionEvent)
            .where(CollectionEvent.session_id == session_id)
            .order_by(CollectionEvent.created_at)
        )
    ).scalars().all()

    out: list[dict] = []
    for ev in events:
        items = (ev.raw_payload or {}).get("attachments")
        if not items:
            continue
        for it in items:
            out.append({
                "filename": it.get("filename"),
                "storage_key": it.get("storage_key"),
                "kind": it.get("kind"),
                "event_id": ev.id,
                "channel": ev.channel,
                "received_at": ev.created_at.isoformat() if ev.created_at else None,
            })
    return out


_EVENT_LABELS = {
    "SEND_ALIMTALK": ("out", "자료요청 발송"),
    "SEND_INVITE": ("out", "초대장 발송"),
    "SEND_CONFIRMATION": ("out", "확인 회신 발송"),
    "FOLLOWUP_SENT": ("out", "후속질문 발송"),
    "PARSE_RESULT": ("system", "AI 파싱 완료"),
    "IMPORT_PAYROLL": ("system", "급여 임포트"),
}
_CHANNEL_KO = {
    "kakao": "카카오톡", "email": "이메일", "sms": "문자",
    "voice": "전화", "manual": "직접", "url": "웹폼",
}


@router.get("/{filing_id}/sessions/{session_id}/timeline")
async def session_timeline(
    filing_id: str,
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """세션(=해당 월) 고객 소통 내역 타임라인.

    direction: out=프로덕트/세무사→고객, in=고객사→서버, system=내부처리.
    """
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    session = await db.get(CollectionSession, session_id)
    if not session or session.monthly_filing_id != filing_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")

    events = (
        await db.execute(
            select(CollectionEvent)
            .where(CollectionEvent.session_id == session_id)
            .order_by(CollectionEvent.created_at)
        )
    ).scalars().all()

    out: list[dict] = []
    for ev in events:
        et = ev.event_type or ""
        if et in _EVENT_LABELS:
            direction, label = _EVENT_LABELS[et]
        elif et.startswith("SEND") or et.endswith("_SENT"):
            direction, label = "out", "발송"
        elif et.startswith("RECEIVE"):
            direction = "in"
            label = "자료 제출 (파싱 실패)" if et.endswith("_UNPARSEABLE") else "자료 제출"
        else:
            direction, label = "system", et or "이벤트"

        atts = (ev.raw_payload or {}).get("attachments") or []
        if atts:
            detail = f"첨부 {len(atts)}건"
        elif ev.raw_text:
            detail = " ".join(ev.raw_text.split())[:60]
        else:
            detail = ""

        at = (
            ev.received_date.isoformat()
            if ev.received_date
            else (ev.created_at.isoformat() if ev.created_at else None)
        )
        out.append({
            "id": ev.id,
            "at": at,
            "direction": direction,
            "channel": _CHANNEL_KO.get(ev.channel or "", ev.channel or ""),
            "event_type": et,
            "label": label,
            "sender_name": ev.sender_name,
            "detail": detail,
        })
    return out


@router.get("/{filing_id}/sessions/{session_id}/attachments/raw")
async def get_attachment(
    filing_id: str,
    session_id: str,
    key: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """첨부파일 원본 스트림 — storage_key가 이 세션에 속하는지 확인 후 반환."""
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    # storage_key가 이 세션의 어느 이벤트 첨부에 실제로 등록돼 있는지 확인 (테넌트 가드)
    events = (
        await db.execute(
            select(CollectionEvent).where(CollectionEvent.session_id == session_id)
        )
    ).scalars().all()
    matched_meta = None
    for ev in events:
        for it in (ev.raw_payload or {}).get("attachments", []):
            if it.get("storage_key") == key:
                matched_meta = it
                break
        if matched_meta:
            break
    if not matched_meta:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found in this session")

    from app.services.storage import get_storage
    storage = get_storage()
    try:
        blob = storage.get_object(key)
    except Exception as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"파일을 찾을 수 없습니다: {e}") from e

    media_type = _attachment_mime(matched_meta.get("kind"), matched_meta.get("filename") or "")
    return Response(content=blob, media_type=media_type)


@router.delete("/{filing_id}/sessions/{session_id}/attachments")
async def delete_attachment(
    filing_id: str,
    session_id: str,
    key: str,
    deleted_by: str = "",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """첨부파일 soft-delete — 이벤트의 raw_payload에서 해당 attachment를 제거."""
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    events = (
        await db.execute(
            select(CollectionEvent).where(CollectionEvent.session_id == session_id)
        )
    ).scalars().all()

    found = False
    for ev in events:
        payload = ev.raw_payload or {}
        atts = payload.get("attachments", [])
        new_atts = [a for a in atts if a.get("storage_key") != key]
        if len(new_atts) < len(atts):
            found = True
            # 삭제 이력 보존
            deleted = [a for a in atts if a.get("storage_key") == key]
            payload["attachments"] = new_atts
            payload.setdefault("deleted_attachments", []).extend(
                {**d, "deleted_by": deleted_by} for d in deleted
            )
            ev.raw_payload = payload
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(ev, "raw_payload")

    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attachment not found")

    # 연결된 PayrollEntry도 삭제
    linked_entries = (
        await db.execute(
            select(PayrollEntry).where(
                PayrollEntry.collection_session_id == session_id,
                PayrollEntry.monthly_filing_id == filing_id,
            )
        )
    ).scalars().all()
    for entry in linked_entries:
        # 이벤트에 첨부만 있고 텍스트 입력이 없었던 경우 — 엔트리도 함께 삭제
        ev = next((e for e in events if e.id == entry.collection_event_id), None)
        if ev and not (ev.raw_payload or {}).get("attachments"):
            await db.delete(entry)

    await db.commit()
    return {"deleted": True}


@router.delete("/{filing_id}/sessions/{session_id}/events/{event_id}")
async def delete_event(
    filing_id: str,
    session_id: str,
    event_id: str,
    deleted_by: str = "",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """텍스트 이벤트 삭제 — 이벤트 + 연결된 PayrollEntry 삭제."""
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    event = await db.get(CollectionEvent, event_id)
    if not event or event.session_id != session_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Event not found")

    # 연결된 PayrollEntry 삭제
    linked = (
        await db.execute(
            select(PayrollEntry).where(PayrollEntry.collection_event_id == event_id)
        )
    ).scalars().all()
    for entry in linked:
        await db.delete(entry)

    # 이벤트 자체 삭제
    await db.delete(event)
    await db.commit()
    return {"deleted": True, "entries_removed": len(linked)}


def _attachment_mime(kind: str | None, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if kind == "image":
        return {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
    if kind == "pdf":
        return "application/pdf"
    if kind == "audio":
        return {"mp3": "audio/mpeg", "m4a": "audio/mp4", "wav": "audio/wav"}.get(ext, "audio/mpeg")
    if kind == "excel":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if kind == "csv":
        return "text/csv"
    return "application/octet-stream"


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
) -> list[PayrollEntryOut]:
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")
    rows = (
        await db.execute(
            select(PayrollEntry)
            .where(PayrollEntry.monthly_filing_id == filing_id)
            .options(selectinload(PayrollEntry.collection_event))
        )
    ).scalars().all()

    from app.schemas.filings import SourceEventOut
    out: list[PayrollEntryOut] = []
    for r in rows:
        entry_out = PayrollEntryOut.model_validate(r)
        if r.collection_event:
            ev = r.collection_event
            entry_out.source_event = SourceEventOut(
                id=ev.id,
                channel=ev.channel,
                sender_name=ev.sender_name,
                received_date=ev.received_date,
                raw_text=ev.raw_text[:500] if ev.raw_text else None,
                created_at=ev.created_at.isoformat() if ev.created_at else None,
            )
        out.append(entry_out)
    return out


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
            # 거래처 세팅(요율 오버라이드 + apply 플래그) 반영 (plan.md 3.8).
            from app.services.payroll_defaults import load_payroll_defaults
            defaults = await load_payroll_defaults(db, entry.client_id)
            si = defaults.social_insurance(entry.taxable, entry.income_type)
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
    client_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """급여대장 엑셀 다운로드. client_id가 있으면 해당 업체만."""
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    filters = [
        PayrollEntry.monthly_filing_id == filing_id,
    ]
    if client_id:
        filters.append(PayrollEntry.client_id == client_id)

    all_entries = (
        await db.execute(
            select(PayrollEntry)
            .where(*filters)
            .options(selectinload(PayrollEntry.employee))
        )
    ).scalars().all()

    # 승인된 항목 우선, 없으면 전체 항목으로 fallback
    entries = [e for e in all_entries if e.approved]
    if not entries:
        entries = list(all_entries)
    if not entries:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "엔트리가 없습니다.",
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


async def _wage_entries_for_filing(
    filing_id: str, db: AsyncSession, client_id: str | None = None
) -> list[PayrollEntry]:
    filters = [
        PayrollEntry.monthly_filing_id == filing_id,
        PayrollEntry.income_type == "WAGE",
        PayrollEntry.employee_id.isnot(None),
    ]
    if client_id:
        filters.append(PayrollEntry.client_id == client_id)
    return list(
        (
            await db.execute(
                select(PayrollEntry)
                .where(*filters)
                .options(selectinload(PayrollEntry.employee))
            )
        )
        .scalars()
        .all()
    )


@router.get("/{filing_id}/insurance-acquisition")
async def download_insurance_acquisition(
    filing_id: str,
    client_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """4대 보험 자격취득 신고서 엑셀 다운로드. client_id 시 해당 거래처만."""
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    entries = await _wage_entries_for_filing(filing_id, db, client_id)
    blob = generate_acquisition_report(entries, period=filing.period)
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="insurance_acquisition_{filing.period}.xlsx"'
            ),
        },
    )


@router.get("/{filing_id}/insurance-loss")
async def download_insurance_loss(
    filing_id: str,
    client_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """4대 보험 자격상실 신고서 엑셀 다운로드. client_id 시 해당 거래처만."""
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    entries = await _wage_entries_for_filing(filing_id, db, client_id)
    blob = generate_loss_report(entries, period=filing.period)
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="insurance_loss_{filing.period}.xlsx"'
            ),
        },
    )


@router.get("/{filing_id}/insurance-change")
async def download_insurance_change(
    filing_id: str,
    client_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """4대 보험 보수월액 변경 신고서 엑셀 다운로드. client_id 시 해당 거래처만."""
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    entries = await _wage_entries_for_filing(filing_id, db, client_id)
    blob = generate_remuneration_change_report(entries, period=filing.period)
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="insurance_change_{filing.period}.xlsx"'
            ),
        },
    )


@router.get("/{filing_id}/insurance-combined")
async def download_insurance_combined(
    filing_id: str,
    client_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """4대 보험 통합 — 3시트 단일 워크북. client_id 시 해당 거래처만."""
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    entries = await _wage_entries_for_filing(filing_id, db, client_id)
    blob = generate_combined_insurance_report(entries, period=filing.period)
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="insurance_combined_{filing.period}.xlsx"'
            ),
        },
    )


@router.get("/{filing_id}/insurance-summary", response_model=InsuranceSummaryOut)
async def get_insurance_summary(
    filing_id: str,
    client_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InsuranceSummaryOut:
    """4대보험 신고 대상 3종 분류·상세 JSON.

    엑셀(insurance-acquisition/loss/change/combined)과 동일한 분류·판정 로직
    (insurance_excel._is_*_target / _change_judgment) 단일 소스에서 파생.
    화면용이므로 RRN 은 마지막 4자리만 노출.
    """
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    entries = await _wage_entries_for_filing(filing_id, db, client_id)
    summary = build_insurance_summary(entries, period=filing.period)
    return InsuranceSummaryOut.model_validate(summary)


@router.get("/{filing_id}/payslips")
async def download_payslips(
    filing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    """급여(임금)명세서 — 근로기준법 §48, 직원별 시트 단일 워크북. 다운로드 전용."""
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
                .options(
                    selectinload(PayrollEntry.employee),
                    selectinload(PayrollEntry.client),
                )
            )
        )
        .scalars()
        .all()
    )
    blob = generate_payslips(entries, period=filing.period)
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="payslips_{filing.period}.xlsx"'
            ),
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
        session, _, _ = await send_invite_to_client(db, filing, client, office_name)
        out.append(_session_out(session, client))

    filing.status = MonthlyFilingStatus.COLLECTING
    filing.total_clients = len(out)
    await db.commit()
    return out
