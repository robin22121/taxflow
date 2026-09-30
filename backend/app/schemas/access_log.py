from datetime import datetime

from pydantic import BaseModel


class AccessLogOut(BaseModel):
    id: str
    created_at: datetime
    user_id: str | None
    user_name: str | None = None
    ip: str | None
    action: str
    client_id: str | None
    client_name: str | None = None
    subject_employee_id: str | None
    endpoint: str | None

    model_config = {"from_attributes": True}
