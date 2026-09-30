from pydantic import BaseModel, field_validator


class StaffOut(BaseModel):
    id: str
    name: str
    login_code: str | None
    role: str
    can_write: bool
    is_active: bool
    assigned_client_count: int = 0

    model_config = {"from_attributes": True}


class StaffCreate(BaseModel):
    name: str
    password: str
    can_write: bool = True

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("비밀번호는 6자리 이상이어야 합니다")
        if not any(c in "!@#$%^&*()_+-=[]{}|;:',.<>?/~`" for c in v):
            raise ValueError("비밀번호에 특수문자를 포함해야 합니다")
        return v


class StaffUpdate(BaseModel):
    name: str | None = None
    can_write: bool | None = None
    is_active: bool | None = None
