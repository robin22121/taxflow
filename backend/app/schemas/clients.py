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
