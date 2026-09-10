"""add_client_portal_pin

사업주 포털 PIN 게이트용 컬럼 추가 (plan/12-owner-portal.md §5.3).
상설 링크 토큰 자체는 기존 secure_tokens 테이블을 재사용하므로 스키마 변경이 없다.

Revision ID: b1c2d3e4f5a6
Revises: a9b0c1d2e3f4
Create Date: 2026-09-10 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a9b0c1d2e3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in sa_inspect(bind).get_columns("clients")}
    if "portal_pin_hash" not in existing:
        op.add_column("clients", sa.Column("portal_pin_hash", sa.String(128), nullable=True))
    if "portal_pin_locked_until" not in existing:
        op.add_column(
            "clients",
            sa.Column("portal_pin_locked_until", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("clients", "portal_pin_locked_until")
    op.drop_column("clients", "portal_pin_hash")
