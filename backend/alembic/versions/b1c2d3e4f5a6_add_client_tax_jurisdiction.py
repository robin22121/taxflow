"""add_client_tax_jurisdiction

거래처 관할세무서 (plan/16 §12) — 위하고 수임처관리 "수임기업 담당세무서" 필드를
이지원천으로 가져온다. 지방세 신고 등에서 참고용으로 쓴다.

Revision ID: b1c2d3e4f5a6
Revises: a7b8c9d0e1f2
Create Date: 2026-09-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("clients") as batch:
        batch.add_column(sa.Column("tax_jurisdiction", sa.String(50), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("clients") as batch:
        batch.drop_column("tax_jurisdiction")
