"""add_employee_change_requests

사업주 포털 입·퇴사 통보 테이블 (plan/12-owner-portal.md §5.2).
주민번호 컬럼을 두지 않아 평문 RRN이 구조적으로 유입될 수 없다.

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-09-10 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if "employee_change_requests" in sa_inspect(bind).get_table_names():
        return
    op.create_table(
        "employee_change_requests",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_id", sa.String(32), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("change_type", sa.String(10), nullable=False),
        sa.Column("employee_id", sa.String(32), sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("hired_at", sa.Date(), nullable=True),
        sa.Column("resigned_at", sa.Date(), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("submitted_via", sa.String(30), nullable=False, server_default="OWNER_PORTAL"),
        sa.Column("status", sa.String(10), nullable=False, server_default="PENDING"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_change_req_client", "employee_change_requests", ["client_id"])
    op.create_index("ix_change_req_status", "employee_change_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_change_req_status", table_name="employee_change_requests")
    op.drop_index("ix_change_req_client", table_name="employee_change_requests")
    op.drop_table("employee_change_requests")
