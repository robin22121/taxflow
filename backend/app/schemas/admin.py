"""서버 관리자(슈퍼어드민) 회원 관리 스키마."""

from datetime import date, datetime

from pydantic import BaseModel


class PromotionOut(BaseModel):
    id: str
    name: str
    discount: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    memo: str | None = None
    granted_by: str | None = None
    created_at: datetime


class PromotionCreate(BaseModel):
    name: str
    discount: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    memo: str | None = None


class OfficeSummary(BaseModel):
    id: str
    name: str
    business_number: str | None = None
    representative: str | None = None
    phone: str | None = None
    email: str | None = None
    short_code: str | None = None
    approval_status: str
    customer_class: str
    subscription_start: date | None = None
    subscription_end: date | None = None
    admin_memo: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    user_count: int = 0
    promotion_count: int = 0


class OfficeDetail(OfficeSummary):
    promotions: list[PromotionOut] = []


class OfficeUpdate(BaseModel):
    customer_class: str | None = None
    subscription_start: date | None = None
    subscription_end: date | None = None
    admin_memo: str | None = None
