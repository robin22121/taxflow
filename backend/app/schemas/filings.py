from datetime import date

from pydantic import BaseModel, Field


class MonthlyFilingCreate(BaseModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")


class MonthlyFilingOut(BaseModel):
    id: str
    period: str
    status: str
    total_clients: int
    total_entries: int

    model_config = {"from_attributes": True}


class CollectionSessionOut(BaseModel):
    id: str
    client_id: str
    client_name: str
    status: str
    request_token: str
    has_responses: bool
    has_anomalies: bool
    entry_count: int


class FilingDashboard(BaseModel):
    filing: MonthlyFilingOut
    sessions: list[CollectionSessionOut]


class SourceEventOut(BaseModel):
    id: str
    channel: str | None
    sender_name: str | None
    received_date: date | None
    raw_text: str | None
    created_at: str | None

    model_config = {"from_attributes": True}


class PayrollEntryOut(BaseModel):
    id: str
    client_id: str
    employee_id: str | None
    collection_event_id: str | None = None
    raw_name: str
    income_type: str
    a_code: str | None
    business_type_code: str | None
    total_amount: int
    salary_amount: int | None
    bonus_amount: int | None
    non_taxable: int
    meal_amount: int = 0
    car_amount: int = 0
    childcare_amount: int = 0
    taxable: int
    national_pension: int = 0
    health_insurance: int = 0
    employment_insurance: int = 0
    longterm_care: int = 0
    income_tax: int
    local_tax: int
    payment_date: date | None
    match_status: str
    prev_amount: int | None
    anomaly_notes: dict | None
    approved: bool
    source_event: SourceEventOut | None = None

    model_config = {"from_attributes": True}


class PayrollEntryUpdate(BaseModel):
    raw_name: str | None = None
    total_amount: int | None = None
    salary_amount: int | None = None
    bonus_amount: int | None = None
    non_taxable: int | None = None
    meal_amount: int | None = None
    car_amount: int | None = None
    childcare_amount: int | None = None
    income_type: str | None = None
    national_pension: int | None = None
    health_insurance: int | None = None
    employment_insurance: int | None = None
    longterm_care: int | None = None
    income_tax: int | None = None
    local_tax: int | None = None
    payment_date: date | None = None
    employee_id: str | None = None
    approved: bool | None = None


class CollectMessageIn(BaseModel):
    text: str
    channel: str = "manual"  # 'kakao' | 'email' | 'voice' | 'manual'
    sender_name: str = Field(min_length=1, max_length=100, description="발신자 (거래처 담당자 이름)")
    received_date: date = Field(description="거래처가 보낸 날짜")


class CollectMessageOut(BaseModel):
    session_id: str
    matched: int
    new_hire_suspected: int
    resignation_suspected: int
    ambiguous: int
    needs_followup: int
    unconfirmed: int = 0  # 전월 대비 미언급 직원 — 계속근무/퇴사 확인 필요


# ---------------------------------------------------------------------------
# AI 파싱 미리보기 — 저장 전 검토용 (dry-run) + 검토 결과 확정 저장
# ---------------------------------------------------------------------------


class ParsedEntryPreview(BaseModel):
    """AI가 읽어낸 급여 항목 1건. 사용자가 검토·수정한 뒤 그대로 commit에 되돌려 보낸다."""

    raw_name: str = Field(min_length=1, max_length=100)
    employee_id: str | None = None
    employee_name: str | None = None  # 매칭된 직원 마스터의 이름 (표시용)
    income_type: str
    total_amount: int = Field(ge=0)
    non_taxable: int = Field(default=0, ge=0)
    meal_amount: int = Field(default=0, ge=0)
    car_amount: int = Field(default=0, ge=0)
    childcare_amount: int = Field(default=0, ge=0)
    match_status: str
    prev_amount: int | None = None
    needs_followup: bool = False
    anomaly_notes: dict | None = None


class CollectPreviewOut(BaseModel):
    session_id: str
    source_text: str
    channel: str
    kind: str | None = None  # 파일 업로드일 때 intake 종류 (excel/csv/image/pdf...)
    attachments: list[dict] | None = None
    entries: list[ParsedEntryPreview]
    new_hire_suspected: int = 0
    resignation_suspected: int = 0
    ambiguous: int = 0
    unconfirmed: int = 0


class CollectCommitIn(BaseModel):
    """미리보기에서 검토·수정한 항목을 실제로 저장."""

    text: str
    channel: str = "manual"
    sender_name: str = Field(min_length=1, max_length=100)
    received_date: date
    attachments: list[dict] | None = None
    entries: list[ParsedEntryPreview] = Field(max_length=500)


# ---------------------------------------------------------------------------
# 4대보험 요약 — 화면용 JSON (insurance_excel.InsuranceSummary 와 1:1 매핑)
# ---------------------------------------------------------------------------


class InsuranceTargetOut(BaseModel):
    """4대보험 신고 대상자 — 자격취득/상실/보수월액변경 공용 (미사용 필드는 None)."""

    kind: str  # "acquisition" | "loss" | "change"
    client_id: str  # 사무소 횡단 화면에서 그룹핑용
    employee_id: str
    name: str
    rrn_last4: str | None = None  # 마스킹 4자리만 (전체 RRN 미노출)
    monthly_wage: int             # 보수월액 (비과세 제외)
    total_amount: int             # 당월 총지급액
    national_pension: int
    health_insurance: int
    longterm_care: int
    employment_insurance: int
    # 자격취득 전용
    hired_at: date | None = None
    acquisition_code: str | None = None
    # 자격상실 전용
    resigned_at: date | None = None
    loss_code: str | None = None
    # 보수월액 변경 전용
    prev_amount: int | None = None
    change_pct: float | None = None
    reason_code: str | None = None
    nps_eligible: bool | None = None
    nps_within_limit: bool | None = None
    nps_consent_required: bool | None = None

    model_config = {"from_attributes": True}


class InsuranceSummaryOut(BaseModel):
    period: str
    acquisitions: list[InsuranceTargetOut]
    losses: list[InsuranceTargetOut]
    changes: list[InsuranceTargetOut]

    model_config = {"from_attributes": True}
