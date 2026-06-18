"""서버 관리자(슈퍼어드민) 전용 — 사무소 가입 승인 + 회원 관리."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_superadmin
from app.models import (
    CustomerClass,
    OfficeApprovalStatus,
    Promotion,
    TaxOffice,
    User,
)
from app.schemas.admin import (
    OfficeDetail,
    OfficeSummary,
    OfficeUpdate,
    PromotionCreate,
    PromotionOut,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _counts(db: AsyncSession) -> tuple[dict[str, int], dict[str, int]]:
    """office_id -> 사용자 수, office_id -> 프로모션 수."""
    user_rows = await db.execute(
        select(User.tax_office_id, func.count())
        .where(User.tax_office_id.is_not(None))
        .group_by(User.tax_office_id)
    )
    promo_rows = await db.execute(
        select(Promotion.tax_office_id, func.count()).group_by(Promotion.tax_office_id)
    )
    return (
        {oid: n for oid, n in user_rows.all()},
        {oid: n for oid, n in promo_rows.all()},
    )


def _summary(office: TaxOffice, user_count: int, promo_count: int) -> OfficeSummary:
    return OfficeSummary(
        id=office.id,
        name=office.name,
        business_number=office.business_number,
        representative=office.representative,
        phone=office.phone,
        email=office.email,
        short_code=office.short_code,
        approval_status=office.approval_status.value,
        customer_class=office.customer_class.value,
        subscription_start=office.subscription_start,
        subscription_end=office.subscription_end,
        admin_memo=office.admin_memo,
        approved_at=office.approved_at,
        created_at=office.created_at,
        user_count=user_count,
        promotion_count=promo_count,
    )


@router.get("/offices", response_model=list[OfficeSummary])
async def list_offices(
    status_filter: str | None = None,
    _admin: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> list[OfficeSummary]:
    """사무소 목록. status_filter=PENDING|APPROVED|REJECTED 로 필터(미지정 시 전체)."""
    stmt = select(TaxOffice).order_by(TaxOffice.created_at.desc())
    if status_filter:
        try:
            stmt = stmt.where(TaxOffice.approval_status == OfficeApprovalStatus(status_filter))
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "잘못된 상태값입니다") from e
    offices = (await db.execute(stmt)).scalars().all()
    user_counts, promo_counts = await _counts(db)
    return [
        _summary(o, user_counts.get(o.id, 0), promo_counts.get(o.id, 0)) for o in offices
    ]


@router.get("/offices/{office_id}", response_model=OfficeDetail)
async def get_office(
    office_id: str,
    _admin: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> OfficeDetail:
    office = await db.get(TaxOffice, office_id)
    if not office:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사무소를 찾을 수 없습니다")
    user_counts, promo_counts = await _counts(db)
    promos = (
        await db.execute(
            select(Promotion)
            .where(Promotion.tax_office_id == office_id)
            .order_by(Promotion.created_at.desc())
        )
    ).scalars().all()
    base = _summary(office, user_counts.get(office.id, 0), promo_counts.get(office.id, 0))
    return OfficeDetail(
        **base.model_dump(),
        promotions=[PromotionOut.model_validate(p, from_attributes=True) for p in promos],
    )


@router.post("/offices/{office_id}/approve", response_model=OfficeSummary)
async def approve_office(
    office_id: str,
    _admin: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> OfficeSummary:
    office = await db.get(TaxOffice, office_id)
    if not office:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사무소를 찾을 수 없습니다")
    office.approval_status = OfficeApprovalStatus.APPROVED
    office.approved_at = datetime.now(UTC)
    await db.commit()
    logger.info("사무소 승인: %s (%s)", office.name, office.id)
    user_counts, promo_counts = await _counts(db)
    return _summary(office, user_counts.get(office.id, 0), promo_counts.get(office.id, 0))


@router.post("/offices/{office_id}/reject", response_model=OfficeSummary)
async def reject_office(
    office_id: str,
    _admin: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> OfficeSummary:
    office = await db.get(TaxOffice, office_id)
    if not office:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사무소를 찾을 수 없습니다")
    office.approval_status = OfficeApprovalStatus.REJECTED
    await db.commit()
    logger.info("사무소 거부: %s (%s)", office.name, office.id)
    user_counts, promo_counts = await _counts(db)
    return _summary(office, user_counts.get(office.id, 0), promo_counts.get(office.id, 0))


@router.patch("/offices/{office_id}", response_model=OfficeSummary)
async def update_office(
    office_id: str,
    payload: OfficeUpdate,
    _admin: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> OfficeSummary:
    office = await db.get(TaxOffice, office_id)
    if not office:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사무소를 찾을 수 없습니다")
    if payload.customer_class is not None:
        try:
            office.customer_class = CustomerClass(payload.customer_class)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "잘못된 고객 분류입니다") from e
    if payload.subscription_start is not None:
        office.subscription_start = payload.subscription_start
    if payload.subscription_end is not None:
        office.subscription_end = payload.subscription_end
    if payload.admin_memo is not None:
        office.admin_memo = payload.admin_memo
    await db.commit()
    user_counts, promo_counts = await _counts(db)
    return _summary(office, user_counts.get(office.id, 0), promo_counts.get(office.id, 0))


@router.post("/offices/{office_id}/promotions", response_model=PromotionOut)
async def add_promotion(
    office_id: str,
    payload: PromotionCreate,
    admin: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> PromotionOut:
    office = await db.get(TaxOffice, office_id)
    if not office:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "사무소를 찾을 수 없습니다")
    promo = Promotion(
        tax_office_id=office_id,
        name=payload.name,
        discount=payload.discount,
        start_date=payload.start_date,
        end_date=payload.end_date,
        memo=payload.memo,
        granted_by=admin.id,
    )
    db.add(promo)
    await db.commit()
    await db.refresh(promo)
    return PromotionOut.model_validate(promo, from_attributes=True)


@router.delete("/promotions/{promotion_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_promotion(
    promotion_id: str,
    _admin: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
) -> None:
    promo = await db.get(Promotion, promotion_id)
    if not promo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "프로모션을 찾을 수 없습니다")
    await db.delete(promo)
    await db.commit()
