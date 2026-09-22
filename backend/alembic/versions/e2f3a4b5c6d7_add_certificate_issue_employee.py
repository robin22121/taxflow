"""add_certificate_issue_employee

직원용 증명서(재직·경력) — 어느 직원의 증명서인지 (plan/17 §4-9).

- certificate_issues.employee_id (nullable FK employees.id) — SQLite 는 batch 필요

Revision ID: e2f3a4b5c6d7
Revises: d0e1f2a3b4c5
Create Date: 2026-09-22 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "d0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("certificate_issues") as batch:
        batch.add_column(sa.Column("employee_id", sa.String(32), nullable=True))
        batch.create_foreign_key(
            "fk_certificate_issues_employee", "employees", ["employee_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("certificate_issues") as batch:
        batch.drop_constraint("fk_certificate_issues_employee", type_="foreignkey")
        batch.drop_column("employee_id")
