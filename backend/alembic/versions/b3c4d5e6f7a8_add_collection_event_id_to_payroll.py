"""add_collection_event_id_to_payroll_entries

Add collection_event_id FK so each PayrollEntry can trace back
to the exact message/event that created it.
Also add sender_name and received_date to CollectionEvent for
manual input metadata.

Revision ID: b3c4d5e6f7a8
Revises: a8f2b3c4d5e6
Create Date: 2026-05-13 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a8f2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add collection_event_id to payroll_entries
    op.add_column(
        "payroll_entries",
        sa.Column("collection_event_id", sa.String(32), sa.ForeignKey("collection_events.id"), nullable=True),
    )
    op.create_index("ix_payroll_event", "payroll_entries", ["collection_event_id"])

    # Add sender_name and received_date to collection_events for manual input metadata
    op.add_column(
        "collection_events",
        sa.Column("sender_name", sa.String(100), nullable=True),
    )
    op.add_column(
        "collection_events",
        sa.Column("received_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("collection_events", "received_date")
    op.drop_column("collection_events", "sender_name")
    op.drop_index("ix_payroll_event", table_name="payroll_entries")
    op.drop_column("payroll_entries", "collection_event_id")
