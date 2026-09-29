"""add_income_type_to_employee

Employee(직원/소득자 마스터)에 소득구분(근로/사업/기타/일용/퇴직)을 추가한다
(plan/02-data-model.md 원래 설계에는 있었지만 구현이 빠져 있었음, "소득지급자 목록"
탭 UI의 기반, 2026-09-29). PayrollEntry.income_type은 월별 항목 단위라 그대로 두고,
Employee.income_type을 마스터 값(기본값)으로 신설한다. 영세사업장 대다수가 근로소득만
다루므로 기본값 WAGE.

Revision ID: c4d5e6f7a8b9
Revises: a1b2c3d4e5f6
Create Date: 2026-09-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("employees") as batch:
        batch.add_column(
            sa.Column(
                "income_type",
                sa.Enum(
                    "WAGE", "BUSINESS", "OTHER", "DAILY", "RETIREMENT",
                    name="incometype", native_enum=False, length=20,
                ),
                nullable=False,
                server_default="WAGE",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("employees") as batch:
        batch.drop_column("income_type")
