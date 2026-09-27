"""add_employee_tax_credit_fields

간이세액표 계산에 쓰는 공제대상가족수·자녀수·조정율을 Employee에 추가하고
(위하고 T 사원등록 공제탭과 대응, plan/16 §13-1 — 2026-09-27 고객센터 확인),
PayrollEntry에도 계산 시점 스냅샷(children·rate_adjust)을 남긴다. 기존
PayrollEntry.dependents는 이미 있던 컬럼이라 손대지 않는다.

- employees: dependents_count(기본 1)·children_count(기본 0)·withholding_rate_adjust(기본 100)
- payroll_entries: children(기본 0)·rate_adjust(기본 100)

Revision ID: a1b2c3d4e5f6
Revises: 9d8e7f6a5b4c
Create Date: 2026-09-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "9d8e7f6a5b4c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("employees") as batch:
        batch.add_column(sa.Column("dependents_count", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column("children_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(
            sa.Column("withholding_rate_adjust", sa.Integer(), nullable=False, server_default="100")
        )

    with op.batch_alter_table("payroll_entries") as batch:
        batch.add_column(sa.Column("children", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("rate_adjust", sa.Integer(), nullable=False, server_default="100"))


def downgrade() -> None:
    with op.batch_alter_table("payroll_entries") as batch:
        batch.drop_column("rate_adjust")
        batch.drop_column("children")

    with op.batch_alter_table("employees") as batch:
        batch.drop_column("withholding_rate_adjust")
        batch.drop_column("children_count")
        batch.drop_column("dependents_count")
