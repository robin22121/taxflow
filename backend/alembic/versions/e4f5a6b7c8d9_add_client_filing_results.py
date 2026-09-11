"""add_client_filing_results

사업주 포털 보관함 — 거래처 × 신고월의 접수증·납부서·가상계좌
(plan/12-owner-portal.md §5.4). 예상 납부세액은 PayrollEntry에서 계산하므로
컬럼을 두지 않는다.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-09-11 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if "client_filing_results" in sa_inspect(bind).get_table_names():
        return
    op.create_table(
        "client_filing_results",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_id", sa.String(32), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("settled_tax", sa.Integer(), nullable=True),
        sa.Column("virtual_account", sa.String(60), nullable=True),
        sa.Column("epayment_number", sa.String(40), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("receipt_key", sa.String(255), nullable=True),
        sa.Column("receipt_name", sa.String(255), nullable=True),
        sa.Column("payment_slip_key", sa.String(255), nullable=True),
        sa.Column("payment_slip_name", sa.String(255), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="MANUAL_UPLOAD"),
        sa.UniqueConstraint("client_id", "period", name="uq_result_client_period"),
    )


def downgrade() -> None:
    op.drop_table("client_filing_results")
