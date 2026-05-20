from datetime import date, datetime

from pydantic import BaseModel


class PlanOut(BaseModel):
    code: str
    label: str
    amount: int
    clients_limit: str
    phase: str


class SubscriptionOut(BaseModel):
    id: str
    plan: str
    plan_label: str
    status: str
    amount: int
    customer_key: str
    card_company: str | None = None
    card_number_masked: str | None = None
    card_type: str | None = None
    current_period_start: date | None = None
    next_billing_date: date | None = None
    canceled_at: datetime | None = None


class RegisterBillingIn(BaseModel):
    auth_key: str
    customer_key: str
    plan: str = "STARTER"


class ChangePlanIn(BaseModel):
    plan: str


class PaymentOut(BaseModel):
    id: str
    order_id: str
    order_name: str
    amount: int
    status: str
    billing_period: str
    method: str | None = None
    failure_message: str | None = None
    receipt_url: str | None = None
    approved_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CronResult(BaseModel):
    charged: int
    failed: int
    skipped: int
    details: list[str]
