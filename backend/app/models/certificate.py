"""증명원 발급 — plan/17-certificate-issuance.md §4-5·§4-9.

발급 요청 한 번 = ``rpa_jobs`` 한 건(kind=CERTIFICATE_ISSUE, 하단 작업바의 칩 하나) +
증명원 종류별 ``certificate_issues`` 여러 건. 에이전트가 발급해 원본은 에이전트 PC
지정 폴더에 두고, 고객 발송용 사본만 서버에 올린다. 사본은 30일 뒤 지운다.
"""

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import Base, IdMixin, TimestampMixin


class CertificateStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"  # 요청됨, 에이전트 대기
    RUNNING = "RUNNING"  # 에이전트가 발급 중
    ISSUED = "ISSUED"  # 발급 완료 — 폴더 저장 + 서버 사본
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class CertificateIssue(Base, IdMixin, TimestampMixin):
    __tablename__ = "certificate_issues"
    __table_args__ = (
        Index("ix_certificate_issues_job", "rpa_job_id"),
        Index("ix_certificate_issues_office_client", "tax_office_id", "client_id"),
        Index("ix_certificate_issues_download_token", "download_token", unique=True),
    )

    tax_office_id: Mapped[str] = mapped_column(ForeignKey("tax_offices.id"))
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    rpa_job_id: Mapped[str] = mapped_column(ForeignKey("rpa_jobs.id"))
    # 직원용 증명서(재직·경력)만 — 서버가 직접 생성한다 (services/employee_certificates)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"))

    cert_type: Mapped[str] = mapped_column(String(40))  # 카탈로그 코드 (services/certificates.CATALOG)
    title: Mapped[str] = mapped_column(String(100))  # 요청 시점 이름 스냅샷
    options: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # {"rrn_disclosed": false}
    status: Mapped[CertificateStatus] = mapped_column(
        Enum(CertificateStatus, native_enum=False, length=20),
        default=CertificateStatus.REQUESTED,
    )
    business_number: Mapped[str | None] = mapped_column(String(20))  # 요청 시점 스냅샷
    business_name: Mapped[str] = mapped_column(String(200))

    # 발급 결과
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    local_path: Mapped[str | None] = mapped_column(String(500))  # 에이전트 PC 원본 위치
    file_key: Mapped[str | None] = mapped_column(String(255))  # 서버 사본 — 만료 시 삭제 후 None
    file_name: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 발급 + 30일
    download_token: Mapped[str | None] = mapped_column(String(64))  # 고객 다운로드 링크
    failure_reason: Mapped[str | None] = mapped_column(Text)

    # 완료 후 다음 작업 — [폴더 열어 확인]이 발송보다 먼저여야 한다
    folder_open_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    folder_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 발송 기록 — [{"channel":"sms","to":"010…","at":"…","accepted":true}]
    deliveries: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
