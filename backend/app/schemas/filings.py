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


class PayrollEntryOut(BaseModel):
    id: str
    client_id: str
    employee_id: str | None
    raw_name: str
    income_type: str
    a_code: str | None
    business_type_code: str | None
    total_amount: int
    salary_amount: int | None
    bonus_amount: int | None
    non_taxable: int
    taxable: int
    income_tax: int
    local_tax: int
    payment_date: date | None
    match_status: str
    prev_amount: int | None
    anomaly_notes: dict | None
    approved: bool

    model_config = {"from_attributes": True}


class PayrollEntryUpdate(BaseModel):
    raw_name: str | None = None
    total_amount: int | None = None
    non_taxable: int | None = None
    income_type: str | None = None
    income_tax: int | None = None
    local_tax: int | None = None
    payment_date: date | None = None
    employee_id: str | None = None
    approved: bool | None = None


class CollectMessageIn(BaseModel):
    text: str
    channel: str = "manual"  # 'kakao' | 'email' | 'voice' | 'manual'


class CollectMessageOut(BaseModel):
    session_id: str
    matched: int
    new_hire_suspected: int
    resignation_suspected: int
    ambiguous: int
    needs_followup: int
