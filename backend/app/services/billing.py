"""구독 정기결제 도메인 로직 — API / cron 엔드포인트 / 스크립트 공용."""

from __future__ import annotations

import calendar
import logging
from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Payment,
    PaymentStatus,
    Subscription,
    SubscriptionStatus,
    TaxOffice,
)
from app.models.billing import PLAN_LABELS, SubscriptionPlan
from app.services.toss import TossError, charge_billing_key

logger = logging.getLogger(__name__)


def add_one_month(d: date) -> date:
    """다음 달 같은 일자(말일 보정)."""
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def _order_id() -> str:
    # uuid hex 32자 — 토스 orderId 규격(6~64, [a-zA-Z0-9-_]) 충족
    return uuid4().hex


def _as_plan(value) -> SubscriptionPlan:
    return value if isinstance(value, SubscriptionPlan) else SubscriptionPlan(value)


async def charge_subscription(
    db: AsyncSession, sub: Subscription, *, period: date | None = None
) -> Payment:
    """단일 구독 1회 청구.

    Payment 레코드를 생성하고, 결과에 따라 구독 상태·다음 청구일을 갱신한 뒤
    커밋한다. 토스 오류는 삼키고 Payment.status=FAILED 로 기록한다.
    """
    period = period or date.today()
    billing_period = period.strftime("%Y-%m")
    plan = _as_plan(sub.plan)
    order_name = f"이지원천 {PLAN_LABELS[plan]} {billing_period}"
    office = await db.get(TaxOffice, sub.tax_office_id)

    payment = Payment(
        subscription_id=sub.id,
        tax_office_id=sub.tax_office_id,
        order_id=_order_id(),
        order_name=order_name,
        amount=sub.amount,
        status=PaymentStatus.PENDING,
        billing_period=billing_period,
        method="카드",
    )
    db.add(payment)

    try:
        data = await charge_billing_key(
            billing_key=sub.toss_billing_key or "",
            customer_key=sub.toss_customer_key,
            amount=sub.amount,
            order_id=payment.order_id,
            order_name=order_name,
            customer_email=office.email if office else None,
            customer_name=office.name if office else None,
        )
        payment.status = PaymentStatus.PAID
        payment.toss_payment_key = data.get("paymentKey")
        payment.method = data.get("method") or "카드"
        receipt = data.get("receipt") or {}
        payment.receipt_url = receipt.get("url")
        approved = data.get("approvedAt")
        try:
            payment.approved_at = (
                datetime.fromisoformat(approved.replace("Z", "+00:00"))
                if approved
                else datetime.now(UTC)
            )
        except ValueError:
            payment.approved_at = datetime.now(UTC)

        # 해지 예약(CANCELED) 상태면 상태는 유지하되 결제는 처리(기간 연장)
        if sub.status != SubscriptionStatus.CANCELED:
            sub.status = SubscriptionStatus.ACTIVE
        sub.current_period_start = period
        sub.next_billing_date = add_one_month(period)
        logger.info(
            "정기결제 성공 office=%s amount=%s period=%s",
            sub.tax_office_id,
            sub.amount,
            billing_period,
        )
    except TossError as e:
        payment.status = PaymentStatus.FAILED
        payment.failure_code = e.code
        payment.failure_message = e.message
        if sub.status == SubscriptionStatus.ACTIVE:
            sub.status = SubscriptionStatus.PAST_DUE
        logger.warning(
            "정기결제 실패 office=%s code=%s msg=%s",
            sub.tax_office_id,
            e.code,
            e.message,
        )

    await db.commit()
    await db.refresh(payment)
    await db.refresh(sub)
    return payment


async def charge_due_subscriptions(
    db: AsyncSession, *, today: date | None = None
) -> dict:
    """next_billing_date 가 도래한 모든 구독을 청구.

    CANCELED 는 제외(청구 중단). PAST_DUE 는 재시도 대상으로 포함.
    """
    today = today or date.today()
    stmt = select(Subscription).where(
        Subscription.status.in_(
            [SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE]
        ),
        Subscription.toss_billing_key.is_not(None),
        Subscription.next_billing_date.is_not(None),
        Subscription.next_billing_date <= today,
    )
    subs = list((await db.execute(stmt)).scalars().all())

    charged = failed = 0
    details: list[str] = []
    for sub in subs:
        p = await charge_subscription(db, sub, period=today)
        if p.status == PaymentStatus.PAID:
            charged += 1
            details.append(f"OK office={sub.tax_office_id} {p.amount}원")
        else:
            failed += 1
            details.append(
                f"FAIL office={sub.tax_office_id} {p.failure_code}:{p.failure_message}"
            )

    return {
        "charged": charged,
        "failed": failed,
        "skipped": 0,
        "details": details,
    }
