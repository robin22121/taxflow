"""결제·구독 — 토스페이먼츠 카드 빌링키 정기결제."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.deps import get_current_user, get_db
from app.models import (
    Payment,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    User,
)
from app.models.billing import (
    PLAN_LABELS,
    PLAN_LIMITS,
    PLAN_PHASE,
    PLAN_PRICING,
    SubscriptionPlan,
)
from app.schemas.billing import (
    ChangePlanIn,
    CronResult,
    PaymentOut,
    PlanOut,
    RegisterBillingIn,
    SubscriptionOut,
)
from app.services.billing import charge_due_subscriptions, charge_subscription
from app.services.toss import TossError, issue_billing_key

logger = logging.getLogger(__name__)

router = APIRouter()


def _customer_key(tax_office_id: str) -> str:
    """사무소별 결정적 customerKey (추측 불가 — uuid 기반 사무소 id)."""
    return f"to_{tax_office_id}"


def _parse_plan(value: str) -> SubscriptionPlan:
    try:
        return SubscriptionPlan(value)
    except ValueError as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"알 수 없는 플랜: {value}"
        ) from e


def _sub_to_out(sub: Subscription) -> SubscriptionOut:
    plan = (
        sub.plan
        if isinstance(sub.plan, SubscriptionPlan)
        else SubscriptionPlan(sub.plan)
    )
    st = sub.status
    return SubscriptionOut(
        id=sub.id,
        plan=plan.value,
        plan_label=PLAN_LABELS[plan],
        status=st.value if hasattr(st, "value") else str(st),
        amount=sub.amount,
        customer_key=sub.toss_customer_key,
        card_company=sub.card_company,
        card_number_masked=sub.card_number_masked,
        card_type=sub.card_type,
        current_period_start=sub.current_period_start,
        next_billing_date=sub.next_billing_date,
        canceled_at=sub.canceled_at,
    )


async def _get_or_create_subscription(
    db: AsyncSession, user: User
) -> Subscription:
    stmt = select(Subscription).where(
        Subscription.tax_office_id == user.tax_office_id
    )
    sub = (await db.execute(stmt)).scalar_one_or_none()
    if sub is None:
        sub = Subscription(
            tax_office_id=user.tax_office_id,
            plan=SubscriptionPlan.STARTER,
            status=SubscriptionStatus.INACTIVE,
            amount=0,
            toss_customer_key=_customer_key(user.tax_office_id),
        )
        db.add(sub)
        await db.commit()
        await db.refresh(sub)
    return sub


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(
    _: User = Depends(get_current_user),
) -> list[PlanOut]:
    return [
        PlanOut(
            code=p.value,
            label=PLAN_LABELS[p],
            amount=PLAN_PRICING[p],
            clients_limit=PLAN_LIMITS[p],
            phase=PLAN_PHASE[p],
        )
        for p in SubscriptionPlan
    ]


@router.get("/subscription", response_model=SubscriptionOut)
async def get_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    sub = await _get_or_create_subscription(db, user)
    return _sub_to_out(sub)


@router.post("/billing-key", response_model=SubscriptionOut)
async def register_billing_key(
    body: RegisterBillingIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    plan = _parse_plan(body.plan)
    sub = await _get_or_create_subscription(db, user)

    if body.customer_key != sub.toss_customer_key:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "customerKey 불일치"
        )

    try:
        data = await issue_billing_key(
            auth_key=body.auth_key, customer_key=body.customer_key
        )
    except TossError as e:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"빌링키 발급 실패 — {e.message}"
        ) from e

    card = data.get("card") or {}
    sub.toss_billing_key = data.get("billingKey")
    sub.card_company = data.get("cardCompany") or card.get("issuerCode")
    sub.card_number_masked = card.get("number")
    sub.card_type = card.get("cardType")
    sub.plan = plan
    sub.amount = PLAN_PRICING[plan]
    if sub.status == SubscriptionStatus.CANCELED:
        sub.status = SubscriptionStatus.INACTIVE
        sub.canceled_at = None
    await db.commit()
    await db.refresh(sub)

    # 첫 달 즉시 결제
    payment = await charge_subscription(db, sub, period=date.today())
    if payment.status == PaymentStatus.FAILED:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"카드는 등록됐으나 첫 결제 실패 — {payment.failure_message}. "
            "결제 재시도를 눌러주세요.",
        )
    return _sub_to_out(sub)


@router.post("/subscription/plan", response_model=SubscriptionOut)
async def change_plan(
    body: ChangePlanIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    plan = _parse_plan(body.plan)
    sub = await _get_or_create_subscription(db, user)
    sub.plan = plan
    sub.amount = PLAN_PRICING[plan]  # 다음 회차부터 신액 적용
    await db.commit()
    await db.refresh(sub)
    return _sub_to_out(sub)


@router.post("/subscription/retry", response_model=SubscriptionOut)
async def retry_payment(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    sub = await _get_or_create_subscription(db, user)
    if not sub.toss_billing_key:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "등록된 카드가 없습니다"
        )
    if sub.status not in (
        SubscriptionStatus.PAST_DUE,
        SubscriptionStatus.INACTIVE,
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "재시도 대상 상태가 아닙니다"
        )
    payment = await charge_subscription(db, sub, period=date.today())
    if payment.status == PaymentStatus.FAILED:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"결제 재시도 실패 — {payment.failure_message}",
        )
    return _sub_to_out(sub)


@router.delete("/subscription", response_model=SubscriptionOut)
async def cancel_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionOut:
    sub = await _get_or_create_subscription(db, user)
    sub.status = SubscriptionStatus.CANCELED
    sub.canceled_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(sub)
    return _sub_to_out(sub)


@router.get("/payments", response_model=list[PaymentOut])
async def list_payments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Payment]:
    stmt = (
        select(Payment)
        .where(Payment.tax_office_id == user.tax_office_id)
        .order_by(Payment.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


@router.post("/cron/charge-due", response_model=CronResult)
async def cron_charge_due(
    x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret"),
    db: AsyncSession = Depends(get_db),
) -> CronResult:
    """도래 구독 일괄 청구 — 스케줄러 전용. X-Cron-Secret 으로 보호."""
    secret = get_settings().billing_cron_secret
    if not secret or x_cron_secret != secret:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
    result = await charge_due_subscriptions(db)
    return CronResult(**result)
