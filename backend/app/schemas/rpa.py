from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RpaAgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RpaAgentOut(BaseModel):
    id: str
    name: str
    last_seen_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RpaAgentIssued(RpaAgentOut):
    token: str  # 발급 응답에서 한 번만 내려준다 — 서버에는 해시만 남는다


# --- 게이트 1 : 위하고 자동입력 작업 등록 --------------------------------


class WehagoUploadCreate(BaseModel):
    filing_id: str
    client_ids: list[str] = Field(min_length=1)


# --- 게이트 2 : 위하고 마감·제작 + 홈택스·위택스 일괄 작업 등록 -----------


class ProductionCreate(BaseModel):
    filing_id: str
    client_ids: list[str] = Field(min_length=1)


# --- 공통 : 작업 표시 --------------------------------------------------


class RpaJobOut(BaseModel):
    id: str
    kind: str
    status: str
    monthly_filing_id: str | None
    client_id: str
    period: str | None
    business_number: str
    business_name: str
    agent_id: str | None
    claimed_at: datetime | None
    finished_at: datetime | None
    result_message: str | None
    step_progress: dict[str, Any] | None = None
    compare_diff: dict[str, Any] | None = None
    acknowledged_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RpaClaimOut(BaseModel):
    job: RpaJobOut | None


# --- 에이전트 회신 ------------------------------------------------------


class RpaJobResultIn(BaseModel):
    status: Literal["SUCCEEDED", "FAILED"]
    message: str | None = Field(default=None, max_length=2000)
    step_progress: dict[str, Any] | None = None
    compare_diff: dict[str, Any] | None = None


class AgentFilingResultIn(BaseModel):
    """에이전트가 홈택스·위택스 접수증·납부서를 서버에 등록할 때 쓰는 요청.

    PDF 실체는 별도 업로드 API(향후) — 지금은 파일 키·이름과 납부 정보만.
    receipt_key/payment_slip_key는 노트북이 서버 저장소에 올린 뒤 그 키를 여기 넣는다 (미구현).
    """

    client_id: str
    period: str
    settled_tax: int | None = None
    virtual_account: str | None = Field(default=None, max_length=60)
    epayment_number: str | None = Field(default=None, max_length=40)
    due_date: date | None = None
    receipt_key: str | None = Field(default=None, max_length=255)
    receipt_name: str | None = Field(default=None, max_length=255)
    payment_slip_key: str | None = Field(default=None, max_length=255)
    payment_slip_name: str | None = Field(default=None, max_length=255)


# --- 접수증·납부서 등록 결과 (게이트 2 이후, 발송 확정 전) -----------------


class FilingResultOut(BaseModel):
    id: str
    client_id: str
    period: str
    settled_tax: int | None
    virtual_account: str | None
    epayment_number: str | None
    due_date: date | None
    receipt_key: str | None
    receipt_name: str | None
    payment_slip_key: str | None
    payment_slip_name: str | None
    published_at: datetime | None  # 게이트 3 통과 전이면 None
    confirmed_by_user_id: str | None
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


# --- 게이트 3 : 발송 확정 응답 -----------------------------------------


class PublishFilingResultOut(FilingResultOut):
    """발송 확정 직후 응답 — published_at·confirmed_by_user_id가 반드시 채워져 있다."""

    published_at: datetime
    confirmed_by_user_id: str


# --- 알림 --------------------------------------------------------------


class RpaNotificationOut(BaseModel):
    id: str
    kind: str
    title: str
    body: str
    job_id: str | None
    filing_result_id: str | None
    read_at: datetime | None
    resent_count: int
    created_at: datetime

    model_config = {"from_attributes": True}
