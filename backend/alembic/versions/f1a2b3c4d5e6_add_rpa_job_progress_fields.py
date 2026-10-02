"""rpa_jobs에 실시간 진행 표시용 컬럼 추가 (current_step, last_progress_at)

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("rpa_jobs") as batch:
        batch.add_column(sa.Column("current_step", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("rpa_jobs") as batch:
        batch.drop_column("last_progress_at")
        batch.drop_column("current_step")
