"""add_rpa_job_acknowledged_at

하단 자동화 작업바 — [확인] 누른 작업을 바에서 내린다 (plan/17-certificate-issuance.md §4-9).

- rpa_jobs.acknowledged_at 추가 (nullable, FK 없음 → batch 불필요)

Revision ID: c9d0e1f2a3b4
Revises: b0c1d2e3f4a5
Create Date: 2026-09-22 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b0c1d2e3f4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("rpa_jobs", sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("rpa_jobs", "acknowledged_at")
