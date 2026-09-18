"""SQLAlchemy 모델. plan/17 §3-9-3.

- agents: 에이전트 등록 (토큰 SHA-256 해시)
- issue_requests: 사용자 발급 요청 (게이트 1)
- jobs: 에이전트 실행 잡 (PENDING → CLAIMED → RUNNING → SUCCEEDED/FAILED)
- certificate_files: 저장된 파일 참조
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from typing import Optional

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from certificate_server.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class CertType(str, enum.Enum):
    BUSINESS_REGISTRATION = "BUSINESS_REGISTRATION"
    TAX_CLEARANCE_ETC = "TAX_CLEARANCE_ETC"
    TAX_PAYMENT_HISTORY = "TAX_PAYMENT_HISTORY"
    INCOME_AMOUNT = "INCOME_AMOUNT"
    VAT_BASE = "VAT_BASE"
    VAT_EXEMPT_INCOME = "VAT_EXEMPT_INCOME"
    BUSINESS_CLOSURE = "BUSINESS_CLOSURE"


class IssueStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    RUNNING = "RUNNING"
    ISSUED = "ISSUED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    last_seen_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)


class CertificateFile(Base):
    __tablename__ = "certificate_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(255))  # ./storage/{id}.png
    mime: Mapped[str] = mapped_column(String(100))
    sha256: Mapped[str] = mapped_column(String(64))
    issued_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    valid_until: Mapped[Optional[dt.date]] = mapped_column(nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class IssueRequest(Base):
    __tablename__ = "issue_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    cert_type: Mapped[CertType] = mapped_column(Enum(CertType))
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    business_number: Mapped[str] = mapped_column(String(20))
    status: Mapped[IssueStatus] = mapped_column(
        Enum(IssueStatus), default=IssueStatus.REQUESTED
    )
    requested_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )
    result_file_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("certificate_files.id"), nullable=True
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    result_file: Mapped[Optional[CertificateFile]] = relationship(
        "CertificateFile", foreign_keys=[result_file_id]
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    issue_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("issue_requests.id")
    )
    agent_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("agents.id"), nullable=True
    )
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.PENDING)
    claimed_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime, nullable=True)
    result_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    issue_request: Mapped[IssueRequest] = relationship("IssueRequest")
