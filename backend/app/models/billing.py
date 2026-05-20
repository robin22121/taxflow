"""결제·구독 — 토스페이먼츠 카드 빌링키 정기결제.

과금 단위는 세무사사무소(TaxOffice). 결제수단은 '카드' 빌링키 단일.
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models._base import IdMixin, TimestampMixin
from app.models.tax_office import TaxOffice


class SubscriptionPlan(str, enum.Enum):
    STARTER = "STARTER"        # 15만원 / 30곳 이하 (Phase 1)
    PRO = "PRO"                # 25만원 / 100곳 (Phase 1+2)
    ENTERPRISE = "ENTERPRISE"  # 50만원~ / 무제한 (전 단계)


class SubscriptionStatus(str, enum.Enum):
    INACTIVE = "INACTIVE"  # 카드(빌링키) 미등록
    ACTIVE = "ACTIVE"      # 정상 — 매월 자동결제
    PAST_DUE = "PAST_DUE"  # 결제 실패 — 다음 회차/수동 재시도 대기
    CANCELED = "CANCELED"  # 해지 — 청구 중단(기간 만료까지 서비스 유지)


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"


# §4.2 가격정책 (월, 원)
PLAN_PRICING: dict[SubscriptionPlan, int] = {
    SubscriptionPlan.STARTER: 150_000,
    SubscriptionPlan.PRO: 250_000,
    SubscriptionPlan.ENTERPRISE: 500_000,
}

PLAN_LABELS: dict[SubscriptionPlan, str] = {
    SubscriptionPlan.STARTER: "스타터",
    SubscriptionPlan.PRO: "프로",
    SubscriptionPlan.ENTERPRISE: "엔터프라이즈",
}

PLAN_LIMITS: dict[SubscriptionPlan, str] = {
    SubscriptionPlan.STARTER: "30곳 이하",
    SubscriptionPlan.PRO: "100곳",
    SubscriptionPlan.ENTERPRISE: "무제한",
}

PLAN_PHASE: dict[SubscriptionPlan, str] = {
    SubscriptionPlan.STARTER: "Phase 1",
    SubscriptionPlan.PRO: "Phase 1 + 2",
    SubscriptionPlan.ENTERPRISE: "전 단계",
}


class Subscription(Base, IdMixin, TimestampMixin):
    """세무사사무소 1곳당 1개 구독."""

    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_office", "tax_office_id", unique=True),
        Index("ix_subscriptions_next_billing", "next_billing_date"),
    )

    tax_office_id: Mapped[str] = mapped_column(ForeignKey("tax_offices.id"))
    plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan, native_enum=False, length=20),
        default=SubscriptionPlan.STARTER,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, native_enum=False, length=20),
        default=SubscriptionStatus.INACTIVE,
    )
    amount: Mapped[int] = mapped_column(Integer, default=0)  # 월 결제액 스냅샷(원)

    # 토스 빌링 — 카드정보는 토스가 보관, 우리는 빌링키만 저장
    toss_customer_key: Mapped[str] = mapped_column(String(64))
    toss_billing_key: Mapped[str | None] = mapped_column(String(200))
    card_company: Mapped[str | None] = mapped_column(String(40))
    card_number_masked: Mapped[str | None] = mapped_column(String(40))
    card_type: Mapped[str | None] = mapped_column(String(20))

    current_period_start: Mapped[date | None] = mapped_column(Date)
    next_billing_date: Mapped[date | None] = mapped_column(Date)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tax_office: Mapped[TaxOffice] = relationship()

    def __repr__(self) -> str:
        return f"<Subscription office={self.tax_office_id} {self.status}>"


class Payment(Base, IdMixin, TimestampMixin):
    """정기결제 1건 이력."""

    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_subscription", "subscription_id"),
        Index("ix_payments_office", "tax_office_id"),
        Index("ix_payments_order", "order_id", unique=True),
    )

    subscription_id: Mapped[str] = mapped_column(ForeignKey("subscriptions.id"))
    tax_office_id: Mapped[str] = mapped_column(ForeignKey("tax_offices.id"))
    order_id: Mapped[str] = mapped_column(String(64))
    order_name: Mapped[str] = mapped_column(String(120))
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, native_enum=False, length=20),
        default=PaymentStatus.PENDING,
    )
    billing_period: Mapped[str] = mapped_column(String(7))  # "YYYY-MM"
    method: Mapped[str | None] = mapped_column(String(20))
    toss_payment_key: Mapped[str | None] = mapped_column(String(200))
    receipt_url: Mapped[str | None] = mapped_column(String(500))
    failure_code: Mapped[str | None] = mapped_column(String(60))
    failure_message: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<Payment {self.order_id} {self.status} {self.amount}>"
