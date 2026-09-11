import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._base import Base, IdMixin, TimestampMixin
from app.models.client import Client
from app.models.employee import Employee


class ChangeType(str, enum.Enum):
    HIRE = "HIRE"
    RESIGN = "RESIGN"


class ChangeRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class EmployeeChangeRequest(Base, IdMixin, TimestampMixin):
    """사업주가 포털에서 통보한 입·퇴사 (plan/12-owner-portal.md §5.2).

    설계 포인트 3가지가 그대로 담겨 있다.

    1. ``MonthlyFiling``이 아니라 ``Client`` 하위다. 입·퇴사는 신고월과 무관하게
       발생하고, 4대보험 자격취득 신고는 입사일 기준 14일 이내라 신고 주기와
       독립적으로 처리돼야 한다.
    2. **주민번호 필드를 두지 않는다.** 이름·날짜만 받으므로 평문 RRN이 구조적으로
       유입될 수 없다 (§4.7 G4를 "탐지"가 아니라 "원천 차단"으로 푸는 채널).
    3. 승인 전까지 ``Employee`` 마스터에 닿지 않는다. 세무사가 승인해야 반영된다.
    """

    __tablename__ = "employee_change_requests"
    __table_args__ = (
        Index("ix_change_req_client", "client_id"),
        Index("ix_change_req_status", "status"),
    )

    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    change_type: Mapped[ChangeType] = mapped_column(
        Enum(ChangeType, native_enum=False, length=10)
    )
    # 퇴사는 기존 직원을 가리키고, 신규 입사는 이름만 온다.
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"))
    name: Mapped[str] = mapped_column(String(100))
    hired_at: Mapped[date | None] = mapped_column(Date)
    resigned_at: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(500))
    submitted_via: Mapped[str] = mapped_column(String(30), default="OWNER_PORTAL")
    status: Mapped[ChangeRequestStatus] = mapped_column(
        Enum(ChangeRequestStatus, native_enum=False, length=10),
        default=ChangeRequestStatus.PENDING,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    client: Mapped[Client] = relationship()
    employee: Mapped[Employee | None] = relationship()
