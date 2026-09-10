"""add_portal_pin_attempts

PIN 시도 제한(5회 실패 → 24시간 잠금)용 실패 횟수 컬럼 추가.
plan/12-owner-portal.md §4.3.3.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-09-10 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in sa_inspect(bind).get_columns("clients")}
    if "portal_pin_failed_count" not in existing:
        op.add_column(
            "clients",
            sa.Column(
                "portal_pin_failed_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    op.drop_column("clients", "portal_pin_failed_count")
