from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import Base, IdMixin, TimestampMixin


class AccessLog(Base, IdMixin, TimestampMixin):
    """접속·접근 기록 — plan/14-accounts-permissions.md §8.1.

    개인정보 안전성 확보조치 기준의 접속기록 보관 의무 이행 수단.
    `created_at`(TimestampMixin)이 곧 §8.1 스펙의 `at`이다. 보관 2년,
    OWNER가 조회 가능. append-only — 절대 수정·삭제하지 않는다.
    """

    __tablename__ = "access_log"
    __table_args__ = (
        Index("ix_access_log_tax_office", "tax_office_id", "created_at"),
        Index("ix_access_log_user", "user_id", "created_at"),
    )

    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    tax_office_id: Mapped[str | None] = mapped_column(ForeignKey("tax_offices.id"), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 최대 길이
    # VIEW | EDIT | DOWNLOAD | DECRYPT_RRN | LOGIN | LOGIN_FAILED
    action: Mapped[str] = mapped_column(String(20))
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    subject_employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(200), nullable=True)
