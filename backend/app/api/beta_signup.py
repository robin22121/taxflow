"""Public beta/earlybird signup endpoints (no auth) — used by the landing page form.

- ``POST /api/v1/beta-signup`` — 사무소 정보 수집 후 저장, 가입 트랙 자동 판정.
- ``GET /api/v1/beta-signup/count`` — 실시간 대기자 카운터용 (기준값 + 실제 건수).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.models.beta_signup import BetaSignup
from app.schemas.beta_signup import BetaSignupCountOut, BetaSignupCreate, BetaSignupOut

router = APIRouter()

# 대기자 카운터 사회적 증거용 기준값 — 실제 신청 건수에 더해 표시.
WAITLIST_BASELINE = 28

# 가입 트랙 마감 (KST 기준 근사, 마감일 포함).
BETA_DEADLINE = date(2026, 8, 31)  # 베타: 6개월 무료 + 이후 12개월 50% (18개월 락인)
EARLYBIRD_DEADLINE = date(2026, 12, 31)  # 얼리버드: 6개월 무료 + 이후 6개월 50%


def _resolve_track(today: date) -> str:
    if today <= BETA_DEADLINE:
        return "beta"
    if today <= EARLYBIRD_DEADLINE:
        return "earlybird"
    return "general"


@router.post("", response_model=BetaSignupOut, status_code=status.HTTP_201_CREATED)
async def create_beta_signup(
    payload: BetaSignupCreate,
    db: AsyncSession = Depends(get_db),
) -> BetaSignup:
    signup = BetaSignup(
        office_name=payload.office_name,
        contact_name=payload.contact_name,
        phone=payload.phone,
        email=payload.email,
        employee_count=payload.employee_count,
        client_count=payload.client_count,
        current_software=payload.current_software,
        note=payload.note,
        track=_resolve_track(datetime.now(UTC).date()),
    )
    db.add(signup)
    await db.commit()
    await db.refresh(signup)
    return signup


@router.get("/count", response_model=BetaSignupCountOut)
async def beta_signup_count(db: AsyncSession = Depends(get_db)) -> BetaSignupCountOut:
    actual = (await db.execute(select(func.count(BetaSignup.id)))).scalar_one()
    return BetaSignupCountOut(count=WAITLIST_BASELINE + actual, actual=actual)
