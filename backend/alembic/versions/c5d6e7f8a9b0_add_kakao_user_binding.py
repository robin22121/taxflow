"""add kakao_user_bindings, kakao_pending_messages tables and tax_offices.short_code

Revision ID: c5d6e7f8a9b0
Revises: b3c4d5e6f7a8
Create Date: 2026-05-14 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tax_offices",
        sa.Column("short_code", sa.String(20), nullable=True),
    )
    op.create_index("ix_tax_offices_short_code", "tax_offices", ["short_code"], unique=True)

    op.create_table(
        "kakao_user_bindings",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("plusfriend_key", sa.String(200), nullable=False),
        sa.Column("tax_office_id", sa.String(32), sa.ForeignKey("tax_offices.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_kakao_binding_key", "kakao_user_bindings", ["plusfriend_key"], unique=True)

    op.create_table(
        "kakao_pending_messages",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("plusfriend_key", sa.String(200), nullable=False),
        sa.Column("tax_office_id", sa.String(32), nullable=False),
        sa.Column("client_id", sa.String(32), nullable=True),
        sa.Column("utterance", sa.Text(), nullable=True),
        sa.Column("file_text", sa.Text(), nullable=True),
        sa.Column("attachments_meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_kakao_pending_key", "kakao_pending_messages", ["plusfriend_key"])


def downgrade() -> None:
    op.drop_index("ix_kakao_pending_key", table_name="kakao_pending_messages")
    op.drop_table("kakao_pending_messages")
    op.drop_index("ix_kakao_binding_key", table_name="kakao_user_bindings")
    op.drop_table("kakao_user_bindings")
    op.drop_index("ix_tax_offices_short_code", table_name="tax_offices")
    op.drop_column("tax_offices", "short_code")
