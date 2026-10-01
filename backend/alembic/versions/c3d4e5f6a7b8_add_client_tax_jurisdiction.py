"""add_client_tax_jurisdiction

거래처 관할세무서 (plan/16 §12) — 위하고 수임처관리 "수임기업 담당세무서" 필드를
이지원천으로 가져온다. 지방세 신고 등에서 참고용으로 쓴다.

Revision ID: c3d4e5f6a7b8
Revises: a7b8c9d0e1f2
Create Date: 2026-09-30 00:00:00.000000

2026-10-01 정정: 원래 이 파일의 revision ID가 기존 마이그레이션
b1c2d3e4f5a6_add_client_portal_pin.py와 중복돼 있어(복사 실수로 추정)
alembic 전체 체인이 CycleDetected로 깨지는 상태였다. 내용은 그대로 두고
revision ID만 고유한 값(c3d4e5f6a7b8)으로 바꿨다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("clients") as batch:
        batch.add_column(sa.Column("tax_jurisdiction", sa.String(50), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("clients") as batch:
        batch.drop_column("tax_jurisdiction")
