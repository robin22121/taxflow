import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import Base, IdMixin, TimestampMixin


class RpaJobKind(str, enum.Enum):
    WEHAGO_PAYROLL_UPLOAD = "WEHAGO_PAYROLL_UPLOAD"  # 위하고T 급여자료입력 엑셀 업로드


class RpaJobStatus(str, enum.Enum):
    PENDING = "PENDING"  # 전송 버튼으로 등록됨, 에이전트 대기
    RUNNING = "RUNNING"  # 에이전트가 가져가 위하고에서 작업 중
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"  # 에이전트가 가져가기 전에 취소


class RpaAgent(Base, IdMixin, TimestampMixin):
    """사무실 PC에 설치된 RPA 에이전트 (plan/16-wehago-rpa.md).

    토큰 원문은 발급 응답에서 한 번만 보여주고 SHA-256 해시만 저장한다.
    PC를 잃어버리면 ``revoked_at``을 채워 즉시 막는다.
    """

    __tablename__ = "rpa_agents"
    __table_args__ = (
        Index("ix_rpa_agents_office", "tax_office_id"),
        Index("ix_rpa_agents_token_hash", "token_hash", unique=True),
    )

    tax_office_id: Mapped[str] = mapped_column(ForeignKey("tax_offices.id"))
    name: Mapped[str] = mapped_column(String(100))  # "사무실 위하고 PC" 등 식별용
    token_hash: Mapped[str] = mapped_column(String(64))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RpaJob(Base, IdMixin, TimestampMixin):
    """에이전트가 처리할 작업 한 건 — 거래처 × 신고월 단위.

    ``business_number``·``business_name``은 등록 시점 스냅샷이다. 에이전트는 이 값으로
    위하고 수임처를 검색하고 화면의 상호와 대조한다.
    """

    __tablename__ = "rpa_jobs"
    __table_args__ = (
        Index("ix_rpa_jobs_office_status", "tax_office_id", "status"),
        Index("ix_rpa_jobs_filing", "monthly_filing_id"),
    )

    tax_office_id: Mapped[str] = mapped_column(ForeignKey("tax_offices.id"))
    kind: Mapped[RpaJobKind] = mapped_column(Enum(RpaJobKind, native_enum=False, length=40))
    status: Mapped[RpaJobStatus] = mapped_column(
        Enum(RpaJobStatus, native_enum=False, length=20),
        default=RpaJobStatus.PENDING,
    )
    monthly_filing_id: Mapped[str] = mapped_column(ForeignKey("monthly_filings.id"))
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    period: Mapped[str] = mapped_column(String(7))  # "YYYY-MM"
    business_number: Mapped[str] = mapped_column(String(20))
    business_name: Mapped[str] = mapped_column(String(200))
    requested_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))

    agent_id: Mapped[str | None] = mapped_column(ForeignKey("rpa_agents.id"))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_message: Mapped[str | None] = mapped_column(Text)
