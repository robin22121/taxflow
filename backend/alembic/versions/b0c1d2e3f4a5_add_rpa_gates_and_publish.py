"""add_rpa_gates_and_publish

3게이트(전송·제작·발송 확정) 정책 반영 — plan/16-wehago-rpa.md §6.

- rpa_jobs.kind 값 WEHAGO_PAYROLL_UPLOAD → WEHAGO_PAYROLL_INPUT (rename in place)
- rpa_jobs에 step_progress·compare_diff JSON 컬럼 추가 (게이트 2 하위 단계·대조 결과)
- client_filing_results에 published_at·confirmed_by_user_id 추가 (게이트 3)
- rpa_notifications 신설 (게이트 2·3 알림 큐)

Revision ID: b0c1d2e3f4a5
Revises: a1c3e5f7b9d2
Create Date: 2026-09-17 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "b0c1d2e3f4a5"
down_revision: str | None = "a1c3e5f7b9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # rpa_jobs.kind rename — 기존 프로덕션 row도 새 이름으로 이관
    op.execute(
        "UPDATE rpa_jobs SET kind = 'WEHAGO_PAYROLL_INPUT' "
        "WHERE kind = 'WEHAGO_PAYROLL_UPLOAD'"
    )

    # rpa_jobs: JSON 컬럼 2개 추가 (FK 없음 → batch 필요 없음)
    op.add_column("rpa_jobs", sa.Column("step_progress", sa.JSON(), nullable=True))
    op.add_column("rpa_jobs", sa.Column("compare_diff", sa.JSON(), nullable=True))

    # client_filing_results: published_at + confirmed_by_user_id (FK) — SQLite에서 batch 필요
    with op.batch_alter_table("client_filing_results") as batch:
        batch.add_column(sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("confirmed_by_user_id", sa.String(32), nullable=True))
        batch.create_foreign_key(
            "fk_client_filing_results_confirmed_by",
            "users",
            ["confirmed_by_user_id"],
            ["id"],
        )

    op.create_table(
        "rpa_notifications",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tax_office_id", sa.String(32), sa.ForeignKey("tax_offices.id"), nullable=False),
        sa.Column("recipient_user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),  # GATE2_REVIEW / GATE3_PUBLISH / FAILURE
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("job_id", sa.String(32), sa.ForeignKey("rpa_jobs.id"), nullable=True),
        sa.Column(
            "filing_result_id",
            sa.String(32),
            sa.ForeignKey("client_filing_results.id"),
            nullable=True,
        ),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resent_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_rpa_notifications_recipient",
        "rpa_notifications",
        ["recipient_user_id", "read_at"],
    )
    op.create_index("ix_rpa_notifications_office", "rpa_notifications", ["tax_office_id"])


def downgrade() -> None:
    op.drop_index("ix_rpa_notifications_office", table_name="rpa_notifications")
    op.drop_index("ix_rpa_notifications_recipient", table_name="rpa_notifications")
    op.drop_table("rpa_notifications")

    with op.batch_alter_table("client_filing_results") as batch:
        batch.drop_constraint("fk_client_filing_results_confirmed_by", type_="foreignkey")
        batch.drop_column("confirmed_by_user_id")
        batch.drop_column("published_at")

    op.drop_column("rpa_jobs", "compare_diff")
    op.drop_column("rpa_jobs", "step_progress")
    op.execute(
        "UPDATE rpa_jobs SET kind = 'WEHAGO_PAYROLL_UPLOAD' "
        "WHERE kind = 'WEHAGO_PAYROLL_INPUT'"
    )
