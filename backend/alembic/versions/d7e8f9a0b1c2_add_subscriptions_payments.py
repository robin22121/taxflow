"""add subscriptions, payments tables (Toss card billing)

Revision ID: d7e8f9a0b1c2
Revises: c5d6e7f8a9b0
Create Date: 2026-05-16 17:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect


# revision identifiers, used by Alembic.
revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    insp = sa_inspect(bind)
    return table in insp.get_table_names()


def upgrade() -> None:
    if not _has_table("subscriptions"):
        op.create_table(
            "subscriptions",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column(
                "tax_office_id",
                sa.String(32),
                sa.ForeignKey("tax_offices.id"),
                nullable=False,
            ),
            sa.Column("plan", sa.String(20), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("toss_customer_key", sa.String(64), nullable=False),
            sa.Column("toss_billing_key", sa.String(200), nullable=True),
            sa.Column("card_company", sa.String(40), nullable=True),
            sa.Column("card_number_masked", sa.String(40), nullable=True),
            sa.Column("card_type", sa.String(20), nullable=True),
            sa.Column("current_period_start", sa.Date(), nullable=True),
            sa.Column("next_billing_date", sa.Date(), nullable=True),
            sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index(
            "ix_subscriptions_office", "subscriptions", ["tax_office_id"], unique=True
        )
        op.create_index(
            "ix_subscriptions_next_billing", "subscriptions", ["next_billing_date"]
        )

    if not _has_table("payments"):
        op.create_table(
            "payments",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column(
                "subscription_id",
                sa.String(32),
                sa.ForeignKey("subscriptions.id"),
                nullable=False,
            ),
            sa.Column(
                "tax_office_id",
                sa.String(32),
                sa.ForeignKey("tax_offices.id"),
                nullable=False,
            ),
            sa.Column("order_id", sa.String(64), nullable=False),
            sa.Column("order_name", sa.String(120), nullable=False),
            sa.Column("amount", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("billing_period", sa.String(7), nullable=False),
            sa.Column("method", sa.String(20), nullable=True),
            sa.Column("toss_payment_key", sa.String(200), nullable=True),
            sa.Column("receipt_url", sa.String(500), nullable=True),
            sa.Column("failure_code", sa.String(60), nullable=True),
            sa.Column("failure_message", sa.Text(), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_payments_subscription", "payments", ["subscription_id"])
        op.create_index("ix_payments_office", "payments", ["tax_office_id"])
        op.create_index("ix_payments_order", "payments", ["order_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_payments_order", table_name="payments")
    op.drop_index("ix_payments_office", table_name="payments")
    op.drop_index("ix_payments_subscription", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_subscriptions_next_billing", table_name="subscriptions")
    op.drop_index("ix_subscriptions_office", table_name="subscriptions")
    op.drop_table("subscriptions")
