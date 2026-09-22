"""add_certificate_issues

증명원 발급 메뉴 — plan/17-certificate-issuance.md §4-5·§4-9.

- certificate_issues 신설 (요청 1건 = rpa_jobs 1건 + 증명원별 행)
- rpa_jobs.monthly_filing_id·period nullable — 증명원 발급 작업은 신고월과 무관

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-22 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("rpa_jobs") as batch:
        batch.alter_column("monthly_filing_id", existing_type=sa.String(32), nullable=True)
        batch.alter_column("period", existing_type=sa.String(7), nullable=True)

    op.create_table(
        "certificate_issues",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("tax_office_id", sa.String(32), sa.ForeignKey("tax_offices.id"), nullable=False),
        sa.Column("client_id", sa.String(32), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("requested_by_user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("rpa_job_id", sa.String(32), sa.ForeignKey("rpa_jobs.id"), nullable=False),
        sa.Column("cert_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("business_number", sa.String(20), nullable=True),
        sa.Column("business_name", sa.String(200), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("local_path", sa.String(500), nullable=True),
        sa.Column("file_key", sa.String(255), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("download_token", sa.String(64), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("folder_open_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("folder_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deliveries", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_certificate_issues_job", "certificate_issues", ["rpa_job_id"])
    op.create_index("ix_certificate_issues_office_client", "certificate_issues", ["tax_office_id", "client_id"])
    op.create_index("ix_certificate_issues_download_token", "certificate_issues", ["download_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_certificate_issues_download_token", table_name="certificate_issues")
    op.drop_index("ix_certificate_issues_office_client", table_name="certificate_issues")
    op.drop_index("ix_certificate_issues_job", table_name="certificate_issues")
    op.drop_table("certificate_issues")
    # 증명원 작업 행이 남아 있으면 NOT NULL 복구가 실패하므로 먼저 지운다
    op.execute(
        "DELETE FROM rpa_notifications WHERE job_id IN "
        "(SELECT id FROM rpa_jobs WHERE kind = 'CERTIFICATE_ISSUE')"
    )
    op.execute("DELETE FROM rpa_jobs WHERE kind = 'CERTIFICATE_ISSUE'")
    with op.batch_alter_table("rpa_jobs") as batch:
        batch.alter_column("period", existing_type=sa.String(7), nullable=False)
        batch.alter_column("monthly_filing_id", existing_type=sa.String(32), nullable=False)
