"""add_portal_messages

사업주 포털 메시지 — 자료 제출 커뮤니케이션 채널 (plan/12-owner-portal.md §3.8, §5.5).
AI가 아닌 세무사무소 직원이 응대한다. 알림을 의도적으로 두지 않는다.

Revision ID: e7f8a9b0c1d2
Revises: c3d4e5f6a7b8
Create Date: 2026-10-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if "portal_messages" in sa_inspect(bind).get_table_names():
        return
    op.create_table(
        "portal_messages",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_id", sa.String(32), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("sender_type", sa.String(10), nullable=False),
        sa.Column("staff_user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("attachment_url", sa.String(500), nullable=True),
        sa.Column("attachment_name", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_portal_messages_client_created",
        "portal_messages",
        ["client_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_portal_messages_client_created", table_name="portal_messages")
    op.drop_table("portal_messages")
