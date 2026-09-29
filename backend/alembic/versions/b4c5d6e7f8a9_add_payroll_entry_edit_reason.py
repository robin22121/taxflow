"""add_payroll_entry_edit_reason

"받은 자료" 탭에서 검토 대상 항목의 승인 버튼을 없애고 수정 버튼으로
대체하면서(편집 = 승인), 금액을 고칠 때 수정 사유를 남길 수 있는 작은
입력칸을 추가했다. 별도 이력 테이블 없이 최신 사유 1건만 보관한다.

Revision ID: b4c5d6e7f8a9
Revises: a1b2c3d4e5f6
Create Date: 2026-09-29 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "b4c5d6e7f8a9"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("payroll_entries") as batch:
        batch.add_column(sa.Column("edit_reason", sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("payroll_entries") as batch:
        batch.drop_column("edit_reason")
