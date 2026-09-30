"""add_payroll_entry_other_income_fields

기타소득(OTHER) 전용 필드 — plan/16 §13-3-3, 위하고T 기타소득자료입력
업로드에 쓴다. necessary_expense(필요경비 금액), other_income_code
(위하고 내부 소득구분 코드, 국세청 a_code와 별개).

Revision ID: c1e4a7b92f03
Revises: 8a81c4f35548
Create Date: 2026-09-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c1e4a7b92f03"
down_revision: str | None = "8a81c4f35548"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("payroll_entries") as batch:
        batch.add_column(
            sa.Column("necessary_expense", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("other_income_code", sa.String(length=10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("payroll_entries") as batch:
        batch.drop_column("other_income_code")
        batch.drop_column("necessary_expense")
