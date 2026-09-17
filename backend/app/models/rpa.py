import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import Base, IdMixin, TimestampMixin


class RpaJobKind(str, enum.Enum):
    WEHAGO_PAYROLL_INPUT = "WEHAGO_PAYROLL_INPUT"  # 게이트 1 후 — 위하고T 급여자료 자동입력만
    MONTHLY_PRODUCTION = "MONTHLY_PRODUCTION"  # 게이트 2 후 — 위하고 원천세·지방세 마감·제작 + 홈택스·위택스 신고 일괄


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

    # MONTHLY_PRODUCTION 작업의 하위 단계 진행 상태.
    # 예: {"wehago_income_tax":"done","wehago_local_tax":"done","hometax":"running","wetax":"pending"}
    step_progress: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # 위하고 계산 vs 이지원천 승인값 대조 결과 — 불일치 항목만 남긴다 (위하고 원본 X, §1-2 ④).
    # 예: {"income_tax":{"expected":123000,"found":124000}}
    compare_diff: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class RpaNotificationKind(str, enum.Enum):
    GATE2_REVIEW = "GATE2_REVIEW"  # 위하고 자동입력 완료 → 사용자 검토·제작 클릭 필요
    GATE3_PUBLISH = "GATE3_PUBLISH"  # 홈택스·위택스 접수증 회수 완료 → 발송 확정 필요
    FAILURE = "FAILURE"  # 어느 단계든 실패·불일치 (§4-3)


class RpaNotification(Base, IdMixin, TimestampMixin):
    """게이트 2·3 및 실패 알림 큐. 로그인 사용자에게 이지원천 알림창으로 뜬다.

    로그아웃 상태였던 사용자도 다음 접속 시 확인할 수 있도록 서버에 남긴다.
    """

    __tablename__ = "rpa_notifications"
    __table_args__ = (
        Index("ix_rpa_notifications_recipient", "recipient_user_id", "read_at"),
        Index("ix_rpa_notifications_office", "tax_office_id"),
    )

    tax_office_id: Mapped[str] = mapped_column(ForeignKey("tax_offices.id"))
    recipient_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[RpaNotificationKind] = mapped_column(
        Enum(RpaNotificationKind, native_enum=False, length=30)
    )
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("rpa_jobs.id"))
    filing_result_id: Mapped[str | None] = mapped_column(ForeignKey("client_filing_results.id"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resent_count: Mapped[int] = mapped_column(Integer, default=0)
