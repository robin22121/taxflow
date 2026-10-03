from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models._base import Base, IdMixin, TimestampMixin


class PayrollEntryChange(Base, IdMixin, TimestampMixin):
    """급여 항목(PayrollEntry) 변경이력 — 누가·언제·무엇을 바꾸거나 지웠는지.

    append-only — 수정·삭제하지 않는다. `entry_id`는 FK가 아니다: 항목이 영구 삭제돼도
    이력은 남아야 한다. 주민번호·계좌번호·원문 텍스트는 절대 담지 않는다(화이트리스트 필드만).
    `created_at`(TimestampMixin)이 변경 시각이다.
    """

    __tablename__ = "payroll_entry_changes"
    __table_args__ = (
        Index("ix_pec_filing_client", "monthly_filing_id", "client_id", "created_at"),
        Index("ix_pec_entry", "entry_id", "created_at"),
    )

    tax_office_id: Mapped[str] = mapped_column(ForeignKey("tax_offices.id"))
    monthly_filing_id: Mapped[str] = mapped_column(ForeignKey("monthly_filings.id"))
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    entry_id: Mapped[str] = mapped_column(String(32))
    employee_id: Mapped[str | None] = mapped_column(String(32))
    subject_name: Mapped[str] = mapped_column(String(100))  # 이름 스냅샷 — 직원이 바뀌어도 이력은 그대로
    income_type: Mapped[str | None] = mapped_column(String(20))
    # CREATE | UPDATE | DELETE | RESTORE | APPROVE | UNAPPROVE | PURGE
    action: Mapped[str] = mapped_column(String(12))
    # UPDATE: {필드: {"before":…, "after":…, "auto":true?}} / DELETE: {"snapshot": {필드: 값}}
    changes: Mapped[dict | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(String(500))
    # manual | collect | portal | carry_forward | import | fast_path | system
    source: Mapped[str] = mapped_column(String(20), default="manual")
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    actor_label: Mapped[str | None] = mapped_column(String(100))  # 사용자 이름 스냅샷 또는 "사장님(포털)" 등
    collection_event_id: Mapped[str | None] = mapped_column(String(32))
    batch_id: Mapped[str | None] = mapped_column(String(32))  # 일괄 작업 묶음
