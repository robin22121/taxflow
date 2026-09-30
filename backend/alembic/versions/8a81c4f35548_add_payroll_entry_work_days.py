"""add_payroll_entry_work_days

일용근로소득(DAILY) 근로일수(공수) 컬럼 — plan/16 §14-2, 위하고T 일용직급여자료입력
"만근공수"(일자=99) 업로드와 tax_calc.py의 일급 환산(daily_count) 계산에 쓴다.

Revision ID: 8a81c4f35548
Revises: b2ad12ba1099
Create Date: 2026-09-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "8a81c4f35548"
down_revision: str | None = "b2ad12ba1099"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("payroll_entries") as batch:
        batch.add_column(sa.Column("work_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("payroll_entries") as batch:
        batch.drop_column("work_days")
