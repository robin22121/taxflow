"""add_beta_signup_table

랜딩 페이지 베타/얼리버드 신청 폼 수집 테이블 추가.
사무소명·담당자·연락처 + 직원 수·거래처 수·현재 SW + 가입 트랙.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "beta_signups",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("office_name", sa.String(200), nullable=False),
        sa.Column("contact_name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(40), nullable=False),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("employee_count", sa.Integer(), nullable=True),
        sa.Column("client_count", sa.Integer(), nullable=True),
        sa.Column("current_software", sa.String(100), nullable=True),
        sa.Column("note", sa.String(1000), nullable=True),
        sa.Column("track", sa.String(20), nullable=False, server_default="general"),
    )


def downgrade() -> None:
    op.drop_table("beta_signups")
