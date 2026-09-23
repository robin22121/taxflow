"""add_wehago_import

위하고 → 이지원천 임포트 (plan/16 §12) — 수임처·사원 기본사항.

- rpa_jobs.client_id·business_number nullable (전체 임포트는 수임처 없음,
  개별 임포트는 아직 이지원천에 없는 수임처일 수 있음) — SQLite 는 batch 필요
- clients: business_type(업태)·business_item(종목)·business_address·wehago_synced_at

Revision ID: f8a9b0c1d2e3
Revises: e2f3a4b5c6d7
Create Date: 2026-09-23 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f8a9b0c1d2e3"
down_revision: str | None = "e2f3a4b5c6d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("rpa_jobs") as batch:
        batch.alter_column("client_id", existing_type=sa.String(32), nullable=True)
        batch.alter_column("business_number", existing_type=sa.String(20), nullable=True)

    with op.batch_alter_table("clients") as batch:
        batch.add_column(sa.Column("business_type", sa.String(100), nullable=True))
        batch.add_column(sa.Column("business_item", sa.String(200), nullable=True))
        batch.add_column(sa.Column("business_address", sa.String(300), nullable=True))
        batch.add_column(sa.Column("wehago_synced_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("clients") as batch:
        batch.drop_column("wehago_synced_at")
        batch.drop_column("business_address")
        batch.drop_column("business_item")
        batch.drop_column("business_type")

    # 임포트 작업을 지워야 NOT NULL 로 되돌릴 수 있다
    op.execute(
        "DELETE FROM rpa_jobs WHERE kind IN ('WEHAGO_MASTER_IMPORT_ALL', 'WEHAGO_CLIENT_IMPORT')"
    )
    with op.batch_alter_table("rpa_jobs") as batch:
        batch.alter_column("business_number", existing_type=sa.String(20), nullable=False)
        batch.alter_column("client_id", existing_type=sa.String(32), nullable=False)
