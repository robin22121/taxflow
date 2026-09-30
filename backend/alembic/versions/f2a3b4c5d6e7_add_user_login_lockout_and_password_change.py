"""add_user_login_lockout_and_password_change

로그인 시도 제한(portal PIN 잠금과 같은 패턴)과 최초 비밀번호 변경 강제
(plan/14-accounts-permissions.md §6.2, §8). 전부 추가·기본값뿐이라
비파괴 — 기존 계정은 must_change_password=False로 시작해 영향 없다.

Revision ID: f2a3b4c5d6e7
Revises: e5f6a7b8c9d0
Create Date: 2026-09-30 00:00:03.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("locked_until")
        batch.drop_column("failed_login_count")
        batch.drop_column("must_change_password")
