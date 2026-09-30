from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import Base, IdMixin, TimestampMixin


class ClientAssignmentHistory(Base, IdMixin, TimestampMixin):
    """거래처 수임담당 배정·재배정 이력 — append-only.

    plan/14-accounts-permissions.md §4. 인수인계 추적 + 개인정보 접근권한
    부여·변경 내역 보관 의무(§8) 증빙을 겸한다. `created_at`(TimestampMixin)이
    곧 changed_at이다 — 행은 수정되지 않고 매 배정마다 새로 쌓인다.
    """

    __tablename__ = "client_assignment_history"
    __table_args__ = (Index("ix_client_assignment_history_client", "client_id"),)

    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    from_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    to_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    changed_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
