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
    client_id: str | None  # 위하고 임포트는 비어 있을 수 있음
    period: str | None
    business_number: str | None  # 전체 임포트만 None
    business_name: str
    agent_id: str | None
    claimed_at: datetime | None
    finished_at: datetime | None
    result_message: str | None
    step_progress: dict[str, Any] | None = None
    compare_diff: dict[str, Any] | None = None
    acknowledged_at: datetime | None = None
    created_at: datetime
    pay_date: date | None = None  # 위하고 급여자료입력 지급일 — claim 응답에만 채운다

    model_config = {"from_attributes": True}


class RpaActivityJobOut(RpaJobOut):
    """하단 작업바 — 다른 직원 작업은 거래처 정보(상호·사업자번호·귀속월·결과 메시지 등)를 비운다."""

    business_name: str | None  # type: ignore[assignment]
    requested_by_name: str | None
    is_mine: bool


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


# --- 위하고 → 이지원천 임포트 (plan/16 §12) -----------------------------


class WehagoClientImportCreate(BaseModel):
    """사업자번호 1건 임포트 — 이지원천에 없으면 새로 등록, 있으면 빈 칸을 채운다."""

    business_number: str = Field(min_length=10, max_length=20)


class WehagoImportEmployeeIn(BaseModel):
    """에이전트가 위하고 사원자료 엑셀에서 뽑은 항목 — 계좌·연락처·보험료는 보내지 않는다."""

    employee_code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=100)
    rrn: str | None = Field(default=None, max_length=20)
    hired_at: date | None = None
    resigned_at: date | None = None
    department: str | None = Field(default=None, max_length=50)
    position: str | None = Field(default=None, max_length=50)
    job_type: str | None = Field(default=None, max_length=50)


class WehagoImportClientIn(BaseModel):
    """수임처 1건 결과. ``error``가 있으면 수집 실패 — 반영 없이 진행 기록만 남긴다."""

    business_number: str = Field(min_length=10, max_length=20)
    business_name: str = Field(min_length=1, max_length=200)
    representative: str | None = Field(default=None, max_length=100)
    is_corporation: bool | None = None
    business_type: str | None = Field(default=None, max_length=100)
    business_item: str | None = Field(default=None, max_length=200)
    business_address: str | None = Field(default=None, max_length=300)
    contact_phone: str | None = Field(default=None, max_length=40)
    employees: list[WehagoImportEmployeeIn] = Field(default_factory=list, max_length=2000)
    total: int | None = Field(default=None, ge=1)  # 전체 임포트의 대상 수임처 수 (진행률)
    error: str | None = Field(default=None, max_length=500)


class WehagoImportClientOut(BaseModel):
    client_id: str | None
    client_created: bool
    employees_created: int
    employees_updated: int
    conflicts: list[dict[str, str]]
