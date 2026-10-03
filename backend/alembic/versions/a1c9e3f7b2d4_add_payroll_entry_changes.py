"""add_payroll_entry_changes

급여 항목 변경이력 테이블 + 고객이 보낸 원래 값(source_snapshot) 컬럼.
기존 소프트 삭제 행(deleted=true)과 수정 사유(edit_reason)는 "기능 도입 이전" 이력으로 옮겨,
삭제 행을 표에서 숨겨도 이력에서 확인·복구할 수 있게 한다. source_snapshot은 NULL로 둔다
(= 원본 미보존, 이전 자료).

Revision ID: a1c9e3f7b2d4
Revises: f1a2b3c4d5e6
Create Date: 2026-10-03 00:00:00.000000
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

from alembic import op

revision: str = "a1c9e3f7b2d4"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_LABEL = "기능 도입 이전"


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa_inspect(bind)

    if "payroll_entry_changes" not in insp.get_table_names():
        op.create_table(
            "payroll_entry_changes",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("tax_office_id", sa.String(32), sa.ForeignKey("tax_offices.id"), nullable=False),
            sa.Column("monthly_filing_id", sa.String(32), sa.ForeignKey("monthly_filings.id"), nullable=False),
            sa.Column("client_id", sa.String(32), sa.ForeignKey("clients.id"), nullable=False),
            sa.Column("entry_id", sa.String(32), nullable=False),
            sa.Column("employee_id", sa.String(32), nullable=True),
            sa.Column("subject_name", sa.String(100), nullable=False),
            sa.Column("income_type", sa.String(20), nullable=True),
            sa.Column("action", sa.String(12), nullable=False),
            sa.Column("changes", sa.JSON(), nullable=True),
            sa.Column("reason", sa.String(500), nullable=True),
            sa.Column("source", sa.String(20), nullable=False),
            sa.Column("actor_user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("actor_label", sa.String(100), nullable=True),
            sa.Column("collection_event_id", sa.String(32), nullable=True),
            sa.Column("batch_id", sa.String(32), nullable=True),
        )
        op.create_index(
            "ix_pec_filing_client", "payroll_entry_changes", ["monthly_filing_id", "client_id", "created_at"]
        )
        op.create_index("ix_pec_entry", "payroll_entry_changes", ["entry_id", "created_at"])

    existing_cols = {c["name"] for c in insp.get_columns("payroll_entries")}
    if "source_snapshot" not in existing_cols:
        op.add_column("payroll_entries", sa.Column("source_snapshot", sa.JSON(), nullable=True))

    _backfill(bind)


def _backfill(bind) -> None:
    """이미 삭제된 행과 수정 사유가 있는 행을 이력으로 옮긴다 (이미 옮겼다면 건너뜀)."""
    entries = sa.table(
        "payroll_entries",
        sa.column("id"), sa.column("monthly_filing_id"), sa.column("client_id"), sa.column("employee_id"),
        sa.column("raw_name"), sa.column("income_type"), sa.column("total_amount"),
        sa.column("updated_at"), sa.column("edit_reason"), sa.column("deleted"),
    )
    clients = sa.table("clients", sa.column("id"), sa.column("tax_office_id"))
    changes = sa.table(
        "payroll_entry_changes",
        sa.column("id"), sa.column("created_at"), sa.column("updated_at"), sa.column("tax_office_id"),
        sa.column("monthly_filing_id"), sa.column("client_id"), sa.column("entry_id"), sa.column("employee_id"),
        sa.column("subject_name"), sa.column("income_type"), sa.column("action"), sa.column("changes", sa.JSON()),
        sa.column("reason"), sa.column("source"), sa.column("actor_label"),
    )

    already = {r[0] for r in bind.execute(sa.select(changes.c.entry_id).where(changes.c.source == "system"))}
    rows = bind.execute(
        sa.select(
            entries.c.id, entries.c.monthly_filing_id, entries.c.client_id, entries.c.employee_id,
            entries.c.raw_name, entries.c.income_type, entries.c.total_amount, entries.c.updated_at,
            entries.c.edit_reason, entries.c.deleted, clients.c.tax_office_id,
        )
        .select_from(entries.join(clients, clients.c.id == entries.c.client_id))
        .where(sa.or_(entries.c.deleted.is_(True), sa.and_(entries.c.edit_reason.is_not(None), entries.c.edit_reason != "")))
    ).all()

    now = datetime.now(UTC)
    out: list[dict] = []
    for r in rows:
        if r.id in already:
            continue
        stamp = r.updated_at or now
        base = dict(
            tax_office_id=r.tax_office_id, monthly_filing_id=r.monthly_filing_id, client_id=r.client_id,
            entry_id=r.id, employee_id=r.employee_id, subject_name=(r.raw_name or "")[:100],
            income_type=str(getattr(r.income_type, "value", r.income_type)) if r.income_type is not None else None,
            source="system", actor_label=LEGACY_LABEL, created_at=stamp, updated_at=stamp,
        )
        if r.edit_reason:
            out.append({**base, "id": uuid4().hex, "action": "UPDATE", "changes": None, "reason": r.edit_reason})
        if r.deleted:
            snap = {"raw_name": r.raw_name, "total_amount": r.total_amount, "income_type": base["income_type"]}
            out.append({**base, "id": uuid4().hex, "action": "DELETE", "changes": {"snapshot": snap}, "reason": None})
    if out:
        op.bulk_insert(changes, out)


def downgrade() -> None:
    with op.batch_alter_table("payroll_entries") as batch:
        batch.drop_column("source_snapshot")
    op.drop_index("ix_pec_entry", table_name="payroll_entry_changes")
    op.drop_index("ix_pec_filing_client", table_name="payroll_entry_changes")
    op.drop_table("payroll_entry_changes")
