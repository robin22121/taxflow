"""pydantic 스키마."""

from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel, ConfigDict

from certificate_server.models import CertType, IssueStatus, JobStatus


class IssueRequestCreate(BaseModel):
    cert_type: CertType
    business_number: str
    options: dict = {}


class IssueRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    cert_type: CertType
    business_number: str
    options: dict
    status: IssueStatus
    requested_at: dt.datetime
    updated_at: dt.datetime
    result_file_id: Optional[str] = None
    failure_reason: Optional[str] = None


class AgentCreate(BaseModel):
    name: str


class AgentCreated(BaseModel):
    id: str
    name: str
    token: str  # 발급 시 1회 노출


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    issue_request_id: str
    status: JobStatus
    # 에이전트가 실행에 필요한 페이로드
    cert_type: CertType
    business_number: str
    options: dict
