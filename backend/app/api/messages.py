"""문자발송 메뉴 — 세목별 신고안내 (plan/13-messaging-activation.md §5).

채널: ``sms`` 문자 / ``alimtalk`` 카톡(알림톡 실패 시 SMS 대체발송).
발송 기록은 수집 세션과 무관하므로 ``MessageLog`` 에 남긴다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.alimtalk import get_alimtalk_channel
from app.channels.base import MessageRecipient, SendResult
from app.channels.sms import get_sms_channel
from app.config import get_settings
from app.core.deps import get_current_user, get_db
from app.models import Client, MessageLog, TaxOffice, User
from app.services.message_templates import (
    FILING_NOTICE_ALIMTALK_BODY,
    FILING_NOTICE_ALIMTALK_CODE,
    FILING_NOTICE_TEMPLATES,
    TAX_TYPE_LABELS,
    fill,
)

router = APIRouter()

TaxType = Literal["WITHHOLDING", "VAT", "INCOME", "CORPORATE"]


class TemplateOut(BaseModel):
    code: str
    tax_type: str
    label: str
    sms_body: str


class TargetsIn(BaseModel):
    tax_type: TaxType
    scope: str = "all"


class TargetOut(BaseModel):
    client_id: str
    business_name: str
    representative: str | None
    contact_phone: str | None
    eligible: bool
    reason: str | None


class TargetsOut(BaseModel):
    items: list[TargetOut]


class SendIn(BaseModel):
    tax_type: TaxType
    channel: Literal["sms", "alimtalk"]
    client_ids: list[str]
    body: str
    deadline: str = ""


class SendResultOut(BaseModel):
    client_id: str
    business_name: str
    accepted: bool
    channel: str
    error: str | None


class SendOut(BaseModel):
    sent: int
    failed: int
    results: list[SendResultOut]


class HistoryItem(BaseModel):
    id: str
    created_at: datetime
    client_id: str | None
    business_name: str | None
    tax_type: str | None
    requested_channel: str
    channel: str
    to_phone: str | None
    body: str
    accepted: bool
    error: str | None


class HistoryOut(BaseModel):
    total: int
    items: list[HistoryItem]


def _excluded_reason(client: Client, tax_type: str, scope: str) -> str | None:
    """세목·범위 조건에 안 맞으면 사유, 맞으면 None."""
    if tax_type == "WITHHOLDING":
        if scope == "monthly" and client.withholding_semiannual:
            return "반기납부"
        if scope == "semiannual" and not client.withholding_semiannual:
            return "매월납부"
    elif tax_type == "VAT":
        if client.vat_type == "EXEMPT":
            return "면세사업자"
        if scope == "general" and client.vat_type != "GENERAL":
            return "일반과세 아님"
        if scope == "simplified" and client.vat_type != "SIMPLIFIED":
            return "간이과세 아님"
    elif tax_type == "INCOME":
        if client.is_corporation:
            return "법인"
        if scope == "sincere" and not client.sincere_filing:
            return "성실신고 대상 아님"
    elif tax_type == "CORPORATE":
        if not client.is_corporation:
            return "개인사업자"
        fy_end = client.fiscal_year_end_month or 12
        if scope == "fy12" and fy_end != 12:
            return f"{fy_end}월 결산"
        if scope == "fy_other" and fy_end == 12:
            return "12월 결산"
    return None


def _target(client: Client, tax_type: str, scope: str) -> TargetOut:
    reason = _excluded_reason(client, tax_type, scope)
    if reason is None and not client.contact_phone:
        reason = "연락처 없음"
    return TargetOut(
        client_id=client.id,
        business_name=client.business_name,
        representative=client.representative,
        contact_phone=client.contact_phone,
        eligible=reason is None,
        reason=reason,
    )


@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(_user: User = Depends(get_current_user)) -> list[TemplateOut]:
    return [
        TemplateOut(code=t.code, tax_type=t.tax_type, label=t.label, sms_body=t.sms_body)
        for t in FILING_NOTICE_TEMPLATES.values()
    ]


@router.post("/filing-notice/targets", response_model=TargetsOut)
async def filing_notice_targets(
    payload: TargetsIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TargetsOut:
    clients = (
        await db.scalars(
            select(Client)
            .where(Client.tax_office_id == user.tax_office_id)
            .order_by(Client.business_name)
        )
    ).all()
    return TargetsOut(items=[_target(c, payload.tax_type, payload.scope) for c in clients])


@router.post("/filing-notice/send", response_model=SendOut)
async def send_filing_notice(
    payload: SendIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SendOut:
    if not payload.client_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "발송할 거래처를 선택하세요")
    if not payload.body.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "문자 본문이 비어 있습니다")

    office = await db.get(TaxOffice, user.tax_office_id)
    office_name = office.name if office else ""
    template = FILING_NOTICE_TEMPLATES[payload.tax_type]
    tax_label = TAX_TYPE_LABELS[payload.tax_type]
    settings = get_settings()
    alimtalk_enabled = settings.kakao_alimtalk_provider in ("aligo", "nhn_cloud")
    sms = get_sms_channel(
        sender=office.sms_sender if office else None, lms_title=f"{tax_label} 신고안내"
    )

    clients = {
        c.id: c
        for c in (
            await db.scalars(
                select(Client).where(
                    Client.tax_office_id == user.tax_office_id,
                    Client.id.in_(payload.client_ids),
                )
            )
        ).all()
    }

    results: list[SendResultOut] = []
    for client_id in payload.client_ids:
        client = clients.get(client_id)
        if client is None:
            continue  # 다른 사무소 거래처·삭제된 거래처는 조용히 제외
        # 세목 조건 재검증 — 범위(scope)는 화면 선택이므로 세목 자체 부적격만 막는다
        reason = _excluded_reason(client, payload.tax_type, "all") or (
            None if client.contact_phone else "연락처 없음"
        )
        if reason:
            results.append(
                SendResultOut(
                    client_id=client.id,
                    business_name=client.business_name,
                    accepted=False,
                    channel="skipped",
                    error=reason,
                )
            )
            continue

        rep = client.representative or ""
        values = {
            "사무소명": office_name,
            "사무소연락처": (office.phone if office else "") or "",
            "거래처명": client.business_name,
            "대표자": f"{rep} " if rep else "",
            "세목": tax_label,
            "신고기한": payload.deadline,
            "준비자료": template.prep_items,
        }
        recipient = MessageRecipient(name=client.business_name, phone=client.contact_phone)

        result: SendResult | None = None
        body = fill(payload.body, values)
        template_code: str | None = None
        alimtalk_error: str | None = None
        if payload.channel == "alimtalk":
            if alimtalk_enabled:
                alimtalk_body = fill(FILING_NOTICE_ALIMTALK_BODY, values, alimtalk=True)
                result = await get_alimtalk_channel().send(
                    recipient, body=alimtalk_body, template_code=FILING_NOTICE_ALIMTALK_CODE
                )
                if result.accepted:
                    body, template_code = alimtalk_body, FILING_NOTICE_ALIMTALK_CODE
                else:
                    alimtalk_error = result.error
            else:
                alimtalk_error = "알림톡 provider 미설정 (KAKAO_ALIMTALK_PROVIDER)"
        if result is None or not result.accepted:
            result = await sms.send(recipient, body=body)
            if not result.accepted and alimtalk_error:
                result.error = f"알림톡: {alimtalk_error} / 문자: {result.error}"

        db.add(
            MessageLog(
                tax_office_id=user.tax_office_id,
                client_id=client.id,
                sent_by=user.id,
                purpose="FILING_NOTICE",
                tax_type=payload.tax_type,
                requested_channel=payload.channel,
                channel=result.channel,
                to_phone=client.contact_phone,
                body=body,
                template_code=template_code,
                accepted=result.accepted,
                provider_msg_id=result.provider_msg_id,
                error=(result.error or "")[:500] or None,
            )
        )
        results.append(
            SendResultOut(
                client_id=client.id,
                business_name=client.business_name,
                accepted=result.accepted,
                channel=result.channel,
                error=result.error,
            )
        )

    await db.commit()
    sent = sum(1 for r in results if r.accepted)
    return SendOut(sent=sent, failed=len(results) - sent, results=results)


@router.get("/history", response_model=HistoryOut)
async def message_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> HistoryOut:
    where = MessageLog.tax_office_id == user.tax_office_id
    total = await db.scalar(select(func.count()).select_from(MessageLog).where(where)) or 0
    rows = (
        await db.execute(
            select(MessageLog, Client.business_name)
            .outerjoin(Client, Client.id == MessageLog.client_id)
            .where(where)
            .order_by(MessageLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return HistoryOut(
        total=total,
        items=[
            HistoryItem(
                id=log.id,
                created_at=log.created_at,
                client_id=log.client_id,
                business_name=name,
                tax_type=log.tax_type,
                requested_channel=log.requested_channel,
                channel=log.channel,
                to_phone=log.to_phone,
                body=log.body,
                accepted=log.accepted,
                error=log.error,
            )
            for log, name in rows
        ],
    )
