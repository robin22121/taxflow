from pydantic import BaseModel, EmailStr, field_validator


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    # 저마찰 가입: 아이디(이메일) + 비밀번호 + 상호만 필수.
    # 사업자번호 등 나머지는 유료 전환 시 수집(선택 입력).
    email: EmailStr
    password: str
    office_name: str
    business_number: str | None = None
    address: str | None = None
    representative: str | None = None
    phone: str | None = None

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
    def biz_number_format(cls, v: str | None) -> str | None:
        if not v:
            return None
        cleaned = v.replace("-", "").replace(" ", "")
        if not cleaned.isdigit() or len(cleaned) != 10:
            raise ValueError("사업자번호는 10자리 숫자여야 합니다")
        return cleaned


class RegisterResponse(BaseModel):
    office_id: str
    short_code: str
    approval_status: str = "PENDING"
    message: str = "가입이 접수되었습니다. 서버 관리자 승인 후 로그인할 수 있습니다."


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
