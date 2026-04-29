from datetime import date

from pydantic import BaseModel, EmailStr


class ClientCreate(BaseModel):
    business_name: str
    business_number: str | None = None
    representative: str | None = None
    contact_phone: str | None = None
    contact_email: EmailStr | None = None


class ClientOut(BaseModel):
    id: str
    business_name: str
    business_number: str | None
    representative: str | None
    contact_phone: str | None
    contact_email: str | None

    model_config = {"from_attributes": True}


class EmployeeCreate(BaseModel):
    name: str
    rrn: str | None = None  # 평문 — 백엔드가 받자마자 암호화 후 폐기
    employee_code: str | None = None
    hired_at: date | None = None


class EmployeeOut(BaseModel):
    id: str
    name: str
    employee_code: str | None
    hired_at: date | None
    resigned_at: date | None
    rrn_last4: str | None
    status: str

    model_config = {"from_attributes": True}
