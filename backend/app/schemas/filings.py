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
