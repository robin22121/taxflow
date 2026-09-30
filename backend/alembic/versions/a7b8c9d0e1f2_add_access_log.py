"""add_access_log

접속·접근 기록 테이블 (plan/14-accounts-permissions.md §8.1). 개인정보
안전성 확보조치 기준의 접속기록 보관 의무 이행 수단 — 신규 테이블만
추가하는 비파괴 마이그레이션.

Revision ID: a7b8c9d0e1f2
Revises: f2a3b4c5d6e7
Create Date: 2026-09-30 00:00:04.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "access_log",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("tax_office_id", sa.String(32), sa.ForeignKey("tax_offices.id"), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("client_id", sa.String(32), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("subject_employee_id", sa.String(32), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("endpoint", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_access_log_tax_office", "access_log", ["tax_office_id", "created_at"])
    op.create_index("ix_access_log_user", "access_log", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_access_log_user", table_name="access_log")
    op.drop_index("ix_access_log_tax_office", table_name="access_log")
    op.drop_table("access_log")
