from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RpaAgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RpaAgentOut(BaseModel):
    id: str
    name: str
    last_seen_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RpaAgentIssued(RpaAgentOut):
    token: str  # 발급 응답에서 한 번만 내려준다 — 서버에는 해시만 남는다


class WehagoUploadCreate(BaseModel):
    filing_id: str
    client_ids: list[str] = Field(min_length=1)


class RpaJobOut(BaseModel):
    id: str
    kind: str
    status: str
    monthly_filing_id: str
    client_id: str
    period: str
    business_number: str
    business_name: str
    agent_id: str | None
    claimed_at: datetime | None
    finished_at: datetime | None
    result_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RpaClaimOut(BaseModel):
    job: RpaJobOut | None


class RpaJobResultIn(BaseModel):
    status: Literal["SUCCEEDED", "FAILED"]
    message: str | None = Field(default=None, max_length=2000)
