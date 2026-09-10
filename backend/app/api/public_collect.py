"""Public (token-based) endpoints used by clients (거래처) without auth.

- ``GET /r/{token}`` — resolve session token to a tiny JSON the frontend uses to render the input page.
- ``POST /r/{token}/submit`` — accepts a free-text payload and runs the full ingestion pipeline.
- ``POST /secure/{token}`` — submit RRN/입사일 for new-hire follow-up.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.collect import _ingest_message
from app.core.deps import get_db
from app.models import Employee, EmploymentStatus, PayrollEntry
from app.schemas.filings import CollectMessageOut
from app.services.crypto import encrypt_rrn, mask_rrn
from app.services.file_intake import intake_file
from app.services.portal import (
    GRANT_TTL,
    PinLockedError,
    ResolvedLink,
    grant_is_valid,
    issue_grant,
    notify_pin_unlock,
    pin_is_set,
    resolve_public_link,
    verify_portal_pin,
)
from app.services.secure_tokens import consume_token, get_active_token
from app.services.storage import get_storage

router = APIRouter()


class CollectionSessionPublic(BaseModel):
    client_name: str
    period: str
    accepts_text: bool = True
    # 상설 링크인데 지금 열린 신고가 없으면 False — 화면은 "보내실 자료 없음"으로 안내한다.
    accepting: bool = True
    # PIN 미발급 거래처는 화면이 게이트 자체를 그리지 않는다 (§4.3.3).
    has_pin: bool = False


class PublicSubmitIn(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class PortalUnlockIn(BaseModel):
    pin: str = Field(pattern=r"^\d{4,8}$")


class PortalUnlockOut(BaseModel):
    grant: str
    expires_in: int


class GatedPayrollRow(BaseModel):
    name: str
    total_amount: int
    prev_amount: int | None


class SecureRrnSubmitIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rrn: str = Field(pattern=r"^\d{6}-?\d{7}$")
    hired_at: date | None = None
    employee_code: str | None = None


async def _require_open_link(db: AsyncSession, token_str: str) -> ResolvedLink:
    """제출 경로 — 링크가 유효하고 지금 자료를 받는 신고가 열려 있어야 한다."""
    link = await resolve_public_link(db, token_str, create_session=True)
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "유효하지 않은 링크입니다")
    if link.filing is None or link.session is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "지금은 보내실 자료가 없습니다. 담당 세무사에게 문의해 주세요.",
        )
    return link


@router.get("/r/{token_str}", response_model=CollectionSessionPublic)
async def resolve_session(token_str: str, db: AsyncSession = Depends(get_db)) -> CollectionSessionPublic:
    link = await resolve_public_link(db, token_str, create_session=False)
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "유효하지 않은 링크입니다")
    return CollectionSessionPublic(
        client_name=link.client.business_name,
        period=link.filing.period if link.filing else "",
        accepting=link.filing is not None,
        has_pin=pin_is_set(link.client),
    )


@router.post("/r/{token_str}/submit", response_model=CollectMessageOut)
async def public_submit_message(
    token_str: str,
    payload: PublicSubmitIn,
    db: AsyncSession = Depends(get_db),
) -> CollectMessageOut:
    link = await _require_open_link(db, token_str)
    return await _ingest_message(
        db=db,
        session=link.session,
        client=link.client,
        filing=link.filing,
        text=payload.text,
        channel="public_url",
    )


@router.post("/r/{token_str}/upload", response_model=CollectMessageOut)
async def public_upload_file(
    token_str: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> CollectMessageOut:
    """공개 토큰으로 파일 업로드 — 음성·엑셀·CSV·이미지를 텍스트로 변환 후 파이프라인 실행."""
    link = await _require_open_link(db, token_str)

    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "빈 파일입니다")
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "25MB 초과 파일은 허용되지 않습니다")

    intake = await intake_file(
        filename=file.filename or "upload",
        content=content,
        storage=get_storage(),
    )
    # 이미지/PDF면 images에 binary가 있고 텍스트는 placeholder뿐일 수 있음 — Vision으로 분석.
    # 그 외(audio/excel/csv)는 텍스트가 비어있으면 거부.
    if not intake.text.strip() and not intake.images:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"파일에서 텍스트를 추출하지 못했습니다 ({intake.kind}). {intake.note or ''}",
        )

    images = intake.images or None
    attachments_meta = (
        [{
            "filename": file.filename or "upload",
            "storage_key": intake.storage_key,
            "kind": intake.kind,
        }]
        if intake.storage_key
        else None
    )

    return await _ingest_message(
        db=db,
        session=link.session,
        client=link.client,
        filing=link.filing,
        text=intake.text,
        channel=f"public_upload_{intake.kind}",
        images=images,
        attachments=attachments_meta,
    )


@router.post("/r/{token_str}/unlock", response_model=PortalUnlockOut)
async def unlock_portal(
    token_str: str,
    payload: PortalUnlockIn,
    db: AsyncSession = Depends(get_db),
) -> PortalUnlockOut:
    """PIN 게이트 통과 — 급여 상세 구역을 여는 단기 grant를 발급한다 (§4.3.3)."""
    link = await resolve_public_link(db, token_str, create_session=False)
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "유효하지 않은 링크입니다")
    if not pin_is_set(link.client):
        # PIN 미발급 거래처는 게이트 뒤 구역 자체를 노출하지 않는다.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "열람할 수 있는 구역이 없습니다")

    try:
        ok = await verify_portal_pin(db, link.client, payload.pin)
    except PinLockedError as e:
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"입력 시도가 많아 잠겼습니다. {e.until:%m월 %d일 %H시} 이후 다시 시도해 주세요.",
        ) from e
    await db.commit()
    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "PIN이 올바르지 않습니다")

    await notify_pin_unlock(link.client)
    return PortalUnlockOut(
        grant=issue_grant(link.client.id),
        expires_in=int(GRANT_TTL.total_seconds()),
    )


@router.get("/r/{token_str}/payroll", response_model=list[GatedPayrollRow])
async def gated_payroll(
    token_str: str,
    x_portal_grant: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[GatedPayrollRow]:
    """게이트 뒤 — 직원별 금액. 게이트 앞 화면은 명단만 본다 (§3.2)."""
    link = await resolve_public_link(db, token_str, create_session=False)
    if not link:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "유효하지 않은 링크입니다")
    if not grant_is_valid(x_portal_grant, link.client.id):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "PIN 확인이 필요합니다")
    if link.filing is None:
        return []

    rows = (
        await db.execute(
            select(PayrollEntry)
            .where(
                PayrollEntry.client_id == link.client.id,
                PayrollEntry.monthly_filing_id == link.filing.id,
            )
            .order_by(PayrollEntry.raw_name)
        )
    ).scalars().all()
    return [
        GatedPayrollRow(
            name=row.raw_name,
            total_amount=row.total_amount,
            prev_amount=row.prev_amount,
        )
        for row in rows
    ]


@router.post("/secure/{token_str}/rrn")
async def submit_rrn(
    token_str: str,
    payload: SecureRrnSubmitIn,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """주민번호·입사일 보안 입력 — 신규 입사자용."""
    try:
        token = await get_active_token(db, token_str)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e

    if token.purpose != "NEW_HIRE_RRN":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "토큰 용도가 일치하지 않습니다")

    rrn_clean = payload.rrn.replace("-", "")
    rrn_formatted = f"{rrn_clean[:6]}-{rrn_clean[6:]}"
    employee = Employee(
        client_id=token.client_id,
        name=payload.name,
        rrn_encrypted=encrypt_rrn(rrn_formatted),
        rrn_last4=rrn_clean[-4:],
        employee_code=payload.employee_code,
        hired_at=payload.hired_at,
        status=EmploymentStatus.ACTIVE,
    )
    db.add(employee)
    await consume_token(db, token)
    await db.commit()
    await db.refresh(employee)
    return {"id": employee.id, "name": employee.name, "masked_rrn": mask_rrn(rrn_formatted)}
