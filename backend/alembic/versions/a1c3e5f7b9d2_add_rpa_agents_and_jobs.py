"""add_rpa_agents_and_jobs

위하고 급여 업로드 RPA — 사무실 PC 에이전트(토큰 해시)와 전송 작업 큐.
plan/16-wehago-rpa.md 참고.

Revision ID: a1c3e5f7b9d2
Revises: f5a6b7c8d9e0
Create Date: 2026-09-14 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "a1c3e5f7b9d2"
down_revision: str | None = "f5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rpa_agents",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tax_office_id", sa.String(32), sa.ForeignKey("tax_offices.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_rpa_agents_office", "rpa_agents", ["tax_office_id"])
    op.create_index("ix_rpa_agents_token_hash", "rpa_agents", ["token_hash"], unique=True)

    op.create_table(
        "rpa_jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tax_office_id", sa.String(32), sa.ForeignKey("tax_offices.id"), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "monthly_filing_id", sa.String(32), sa.ForeignKey("monthly_filings.id"), nullable=False
        ),
        sa.Column("client_id", sa.String(32), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("business_number", sa.String(20), nullable=False),
        sa.Column("business_name", sa.String(200), nullable=False),
        sa.Column(
            "requested_by_user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False
        ),
        sa.Column("agent_id", sa.String(32), sa.ForeignKey("rpa_agents.id"), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_rpa_jobs_office_status", "rpa_jobs", ["tax_office_id", "status"])
    op.create_index("ix_rpa_jobs_filing", "rpa_jobs", ["monthly_filing_id"])


def downgrade() -> None:
    op.drop_index("ix_rpa_jobs_filing", table_name="rpa_jobs")
    op.drop_index("ix_rpa_jobs_office_status", table_name="rpa_jobs")
    op.drop_table("rpa_jobs")
    op.drop_index("ix_rpa_agents_token_hash", table_name="rpa_agents")
    op.drop_index("ix_rpa_agents_office", table_name="rpa_agents")
    op.drop_table("rpa_agents")
