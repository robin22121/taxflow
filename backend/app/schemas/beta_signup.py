from pydantic import BaseModel, Field


class BetaSignupCreate(BaseModel):
    office_name: str = Field(min_length=1, max_length=200)
    contact_name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=1, max_length=40)
    email: str | None = Field(default=None, max_length=200)
    employee_count: int | None = Field(default=None, ge=0)
    client_count: int | None = Field(default=None, ge=0)
    current_software: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=1000)


class BetaSignupOut(BaseModel):
    id: str
    office_name: str
    track: str

    model_config = {"from_attributes": True}


class BetaSignupCountOut(BaseModel):
    count: int  # 화면 표시용 = 기준값(28) + 실제 신청 건수
    actual: int  # 실제 DB 신청 건수
