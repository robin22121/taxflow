"""add_payroll_entry_deleted_flag

원천세관리 "삭제"를 하드 삭제 대신 소프트 삭제로 바꾼다 — 실제 row는 남기고
`deleted=true`만 세워서 화면에는 빨간 취소선으로 표시하되, 신고서 산출물·
집계·전월 매칭 로직에서는 전부 제외한다.

Revision ID: c6d7e8f9a0b1
Revises: b4c5d6e7f8a9
Create Date: 2026-09-29 01:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c6d7e8f9a0b1"
down_revision: str | None = "b4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("payroll_entries") as batch:
        batch.add_column(sa.Column("deleted", sa.Boolean(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("payroll_entries") as batch:
        batch.drop_column("deleted")
