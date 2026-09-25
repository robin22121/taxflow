"""add_client_pay_day

거래처별 급여지급일 (plan/16 §9-3 위하고 급여자료입력 지급일).

- client_payroll_defaults.pay_month_offset: 0 당월 · 1 익월 (null = 미설정)
- client_payroll_defaults.pay_day: 1~31, 31 = 말일 (그달에 없는 날은 말일로)

Revision ID: 9d8e7f6a5b4c
Revises: f8a9b0c1d2e3
Create Date: 2026-09-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "9d8e7f6a5b4c"
down_revision: str | None = "f8a9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("client_payroll_defaults") as batch:
        batch.add_column(sa.Column("pay_month_offset", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("pay_day", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("client_payroll_defaults") as batch:
        batch.drop_column("pay_day")
        batch.drop_column("pay_month_offset")
