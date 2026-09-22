"""add_message_logs_and_client_tax_fields

발송 확장 P0 (plan/13-messaging-activation.md §5.3).

- clients: vat_type, withholding_semiannual, fiscal_year_end_month, sincere_filing (FK 없음 → batch 불필요)
- tax_offices: sms_sender
- message_logs 신설 — 수집 세션과 무관한 발송 기록

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-09-22 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("vat_type", sa.String(length=20), nullable=True))
    op.add_column(
        "clients",
        sa.Column("withholding_semiannual", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column("clients", sa.Column("fiscal_year_end_month", sa.Integer(), nullable=True))
    op.add_column(
        "clients",
        sa.Column("sincere_filing", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column("tax_offices", sa.Column("sms_sender", sa.String(length=40), nullable=True))

    op.create_table(
        "message_logs",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("tax_office_id", sa.String(length=32), sa.ForeignKey("tax_offices.id"), nullable=False),
        sa.Column("client_id", sa.String(length=32), sa.ForeignKey("clients.id"), nullable=True),
        sa.Column("sent_by", sa.String(length=32), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("tax_type", sa.String(length=20), nullable=True),
        sa.Column("requested_channel", sa.String(length=20), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("to_phone", sa.String(length=40), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("template_code", sa.String(length=40), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("provider_msg_id", sa.String(length=100), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_message_logs_office_created", "message_logs", ["tax_office_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_message_logs_office_created", table_name="message_logs")
    op.drop_table("message_logs")
    op.drop_column("tax_offices", "sms_sender")
    with op.batch_alter_table("clients") as batch:
        batch.drop_column("sincere_filing")
        batch.drop_column("fiscal_year_end_month")
        batch.drop_column("withholding_semiannual")
        batch.drop_column("vat_type")
