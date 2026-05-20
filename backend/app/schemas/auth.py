from pydantic import BaseModel, EmailStr, field_validator

_PASSWORD_SPECIALS = "!@#$%^&*()_+-=[]{}|;:',.<>?/~`"


def validate_password_strength(v: str) -> str:
    """비밀번호 강도 규칙 — 6자리 이상 + 특수문자 포함. (가입·변경 공통)"""
    if len(v) < 6:
        raise ValueError("비밀번호는 6자리 이상이어야 합니다")
    if not any(c in _PASSWORD_SPECIALS for c in v):
        raise ValueError("비밀번호에 특수문자를 포함해야 합니다")
    return v


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
        return validate_password_strength(v)

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
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


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
    tax_office_id: str
    is_admin: bool
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


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def new_password_strength(cls, v: str) -> str:
        return validate_password_strength(v)
