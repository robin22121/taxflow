from pydantic import BaseModel, EmailStr, field_validator


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    business_number: str
    password: str
    office_name: str
    address: str
    representative: str
    phone: str
    email: EmailStr

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("비밀번호는 6자리 이상이어야 합니다")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:',.<>?/~`" for c in v):
            raise ValueError("비밀번호에 특수문자를 포함해야 합니다")
        return v

    @field_validator("business_number")
    @classmethod
    def biz_number_format(cls, v: str) -> str:
        cleaned = v.replace("-", "").replace(" ", "")
        if not cleaned.isdigit() or len(cleaned) != 10:
            raise ValueError("사업자번호는 10자리 숫자여야 합니다")
        return cleaned


class RegisterResponse(BaseModel):
    office_id: str
    short_code: str
    approval_status: str = "PENDING"
    message: str = "가입이 완료되었습니다. 바로 로그인하여 이용할 수 있습니다."


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class CurrentUser(BaseModel):
    id: str
    email: str
    name: str
    tax_office_id: str | None = None
    is_admin: bool
    is_superadmin: bool = False
    short_code: str | None = None
    office_name: str | None = None
    office_phone: str | None = None
    office_email: str | None = None
    office_address: str | None = None
    office_representative: str | None = None


class ProfileUpdate(BaseModel):
    name: str | None = None
    office_phone: str | None = None
    office_email: str | None = None
    office_address: str | None = None
    office_representative: str | None = None
