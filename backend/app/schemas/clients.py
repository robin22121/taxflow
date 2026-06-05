from datetime import date

from pydantic import BaseModel


class ClientCreate(BaseModel):
    business_name: str
    business_number: str | None = None
    representative: str | None = None
    contact_phone: str | None = None
    # EmailStr 대신 str — 내부 도메인(.local, .internal 등)도 허용. 형식 오류는
    # 발송 시점에 채널이 처리.
    contact_email: str | None = None
    is_corporation: bool = False


class ClientOut(BaseModel):
    id: str
    business_name: str
    business_number: str | None
    representative: str | None
    contact_phone: str | None
    contact_email: str | None
    is_corporation: bool
    collect_email: str | None = None
    invite_sent: bool = False

    model_config = {"from_attributes": True}


class ClientUpdate(BaseModel):
    business_name: str | None = None
    business_number: str | None = None
    representative: str | None = None
    contact_phone: str | None = None
    contact_email: str | None = None
    is_corporation: bool | None = None


class ChannelAttempt(BaseModel):
    channel: str  # 예: sms_aligo, sms_stub, email_sendgrid, alimtalk_skipped
    accepted: bool
    error: str | None = None


class ClientInviteResult(BaseModel):
    sent: bool
    channels: list[str]  # accepted된 실제 채널명
    attempts: list[ChannelAttempt] = []  # 모든 시도 (성공/실패 포함, UI 진단용)
    filing_period: str
    detail: str | None = None


class EmployeeCreate(BaseModel):
    name: str
    rrn: str | None = None  # 평문 — 백엔드가 받자마자 암호화 후 폐기
    employee_code: str | None = None
    hired_at: date | None = None
    business_type_code: str | None = None  # 사업소득 업종코드 (940xxx)


class EmployeeOut(BaseModel):
    id: str
    name: str
    employee_code: str | None
    hired_at: date | None
    resigned_at: date | None
    rrn_last4: str | None
    status: str
    business_type_code: str | None

    model_config = {"from_attributes": True}


# ─── 거래처별 지급항목·4대보험 기본 세팅 (plan.md 3.8) ───

class PayrollDefaultOut(BaseModel):
    """거래처 세팅값. 레코드가 없으면 시스템 기본값을 채워서 반환한다.
    요율은 모두 백분율(예: 4.5)로 직렬화 — UI에서 그대로 표시·편집.
    """

    meal_default: int = 200_000
    car_default: int = 200_000
    childcare_default: int = 0

    apply_national_pension: bool = True
    apply_health_insurance: bool = True
    apply_employment_insurance: bool = True
    apply_longterm_care: bool = True

    # 백분율로 직렬화. null이면 시스템 기본 요율(GET 시점에 채워 보냄).
    nps_rate_percent: float
    hi_rate_percent: float
    ltc_rate_percent: float  # 건강보험료 대비
    ei_rate_percent: float

    note: str | None = None

    # 시스템 기본 요율 — UI에서 "기본값 안내" 표시용
    system_nps_rate_percent: float
    system_hi_rate_percent: float
    system_ltc_rate_percent: float
    system_ei_rate_percent: float


class PayrollDefaultUpdate(BaseModel):
    """모든 필드 optional — 부분 갱신 가능. 요율은 백분율(예: 4.5)로 입력."""

    meal_default: int | None = None
    car_default: int | None = None
    childcare_default: int | None = None

    apply_national_pension: bool | None = None
    apply_health_insurance: bool | None = None
    apply_employment_insurance: bool | None = None
    apply_longterm_care: bool | None = None

    nps_rate_percent: float | None = None
    hi_rate_percent: float | None = None
    ltc_rate_percent: float | None = None
    ei_rate_percent: float | None = None

    note: str | None = None
