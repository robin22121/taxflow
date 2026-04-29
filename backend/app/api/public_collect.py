"""Public (token-based) endpoints used by clients (거래처) without auth.

- ``GET /r/{token}`` — resolve session token to a tiny JSON the frontend uses to render the input page.
- ``POST /r/{token}/submit`` — accepts a free-text payload and runs the full ingestion pipeline.
- ``POST /secure/{token}`` — submit RRN/입사일 for new-hire follow-up.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.collect import _ingest_message
from app.core.deps import get_db
from app.models import (
    Client,
    CollectionSession,
    Employee,
    EmploymentStatus,
    MonthlyFiling,
)
from app.schemas.filings import CollectMessageOut
from app.services.crypto import encrypt_rrn, mask_rrn
from app.services.file_intake import intake_file
from app.services.secure_tokens import consume_token, get_active_token
from app.services.storage import get_storage
from app.services.stt import get_stt_provider

router = APIRouter()


class CollectionSessionPublic(BaseModel):
    client_name: str
    period: str
    accepts_text: bool = True


class PublicSubmitIn(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class SecureRrnSubmitIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    rrn: str = Field(pattern=r"^\d{6}-?\d{7}$")
    hired_at: date | None = None
    employee_code: str | None = None


@router.get("/r/{token_str}", response_model=CollectionSessionPublic)
async def resolve_session(token_str: str, db: AsyncSession = Depends(get_db)) -> CollectionSessionPublic:
    session = (
        await db.execute(
            select(CollectionSession)
            .where(CollectionSession.request_token == token_str)
            .options(
                selectinload(CollectionSession.client),
                selectinload(CollectionSession.monthly_filing),
            )
        )
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "유효하지 않은 링크입니다")
    return CollectionSessionPublic(
        client_name=session.client.business_name,
        period=session.monthly_filing.period,
    )


@router.post("/r/{token_str}/submit", response_model=CollectMessageOut)
async def public_submit_message(
    token_str: str,
    payload: PublicSubmitIn,
    db: AsyncSession = Depends(get_db),
) -> CollectMessageOut:
    session = (
        await db.execute(
            select(CollectionSession)
            .where(CollectionSession.request_token == token_str)
            .options(
                selectinload(CollectionSession.client),
                selectinload(CollectionSession.monthly_filing),
            )
        )
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "유효하지 않은 링크입니다")
    return await _ingest_message(
        db=db,
        session=session,
        client=session.client,
        filing=session.monthly_filing,
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
    session = (
        await db.execute(
            select(CollectionSession)
            .where(CollectionSession.request_token == token_str)
            .options(
                selectinload(CollectionSession.client),
                selectinload(CollectionSession.monthly_filing),
            )
        )
    ).scalar_one_or_none()
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "유효하지 않은 링크입니다")

    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "빈 파일입니다")
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "25MB 초과 파일은 허용되지 않습니다")

    intake = await intake_file(
        filename=file.filename or "upload",
        content=content,
        storage=get_storage(),
        stt=get_stt_provider(),
    )
    if not intake.text.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"파일에서 텍스트를 추출하지 못했습니다 ({intake.kind}). {intake.note or ''}",
        )

    return await _ingest_message(
        db=db,
        session=session,
        client=session.client,
        filing=session.monthly_filing,
        text=intake.text,
        channel=f"public_upload_{intake.kind}",
    )


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
