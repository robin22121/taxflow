"""add_admin_approval_and_membership

서버 관리자(슈퍼어드민) + 사무소 가입 승인 + 회원 관리(고객분류·구독기간·프로모션) 추가.

- users.is_superadmin 추가, users.tax_office_id nullable 화 (슈퍼어드민은 무소속)
- tax_offices: approval_status / approved_at / customer_class / subscription_* / admin_memo
- promotions 테이블 신설
- 기존 사무소는 APPROVED 로 백필 (락아웃 방지)

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-06-18 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── users: 슈퍼어드민 플래그 + tax_office_id nullable ──
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.alter_column("tax_office_id", existing_type=sa.String(32), nullable=True)

    # ── tax_offices: 승인/회원관리 필드 (기존 행은 APPROVED 로 백필) ──
    op.add_column(
        "tax_offices",
        sa.Column("approval_status", sa.String(20), nullable=False, server_default="APPROVED"),
    )
    op.add_column("tax_offices", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tax_offices",
        sa.Column("customer_class", sa.String(20), nullable=False, server_default="TRIAL"),
    )
    op.add_column("tax_offices", sa.Column("subscription_start", sa.Date(), nullable=True))
    op.add_column("tax_offices", sa.Column("subscription_end", sa.Date(), nullable=True))
    op.add_column("tax_offices", sa.Column("admin_memo", sa.String(1000), nullable=True))

    # ── promotions ──
    op.create_table(
        "promotions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "tax_office_id",
            sa.String(32),
            sa.ForeignKey("tax_offices.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("discount", sa.String(100), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("memo", sa.String(500), nullable=True),
        sa.Column("granted_by", sa.String(32), nullable=True),
    )
    op.create_index("ix_promotions_office", "promotions", ["tax_office_id"])


def downgrade() -> None:
    op.drop_index("ix_promotions_office", table_name="promotions")
    op.drop_table("promotions")

    op.drop_column("tax_offices", "admin_memo")
    op.drop_column("tax_offices", "subscription_end")
    op.drop_column("tax_offices", "subscription_start")
    op.drop_column("tax_offices", "customer_class")
    op.drop_column("tax_offices", "approved_at")
    op.drop_column("tax_offices", "approval_status")

    with op.batch_alter_table("users") as batch:
        batch.alter_column("tax_office_id", existing_type=sa.String(32), nullable=False)
        batch.drop_column("is_superadmin")
