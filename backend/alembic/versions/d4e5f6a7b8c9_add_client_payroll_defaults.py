"""add_client_payroll_defaults

거래처별 지급항목·4대보험 기본 세팅 테이블 추가.
원시파일에 항목이 없을 때 fallback으로 사용 (plan.md 3.8절).

Revision ID: d4e5f6a7b8c9
Revises: c5d6e7f8a9b0
Create Date: 2026-05-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client_payroll_defaults",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "client_id",
            sa.String(32),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("meal_default", sa.Integer(), nullable=False, server_default="200000"),
        sa.Column("car_default", sa.Integer(), nullable=False, server_default="200000"),
        sa.Column("childcare_default", sa.Integer(), nullable=False, server_default="200000"),
        sa.Column("apply_national_pension", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("apply_health_insurance", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("apply_employment_insurance", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("apply_longterm_care", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("nps_rate_override", sa.Numeric(6, 4), nullable=True),
        sa.Column("hi_rate_override", sa.Numeric(6, 4), nullable=True),
        sa.Column("ltc_rate_override", sa.Numeric(6, 4), nullable=True),
        sa.Column("ei_rate_override", sa.Numeric(6, 4), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("client_payroll_defaults")
