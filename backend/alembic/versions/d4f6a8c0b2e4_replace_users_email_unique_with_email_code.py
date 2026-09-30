"""replace_users_email_unique_with_email_code

직원계정은 대표와 같은 email(사업자번호)을 공유하고 login_code로만 구분된다
(plan/14-accounts-permissions.md §6.5) — 전역 email 유일 인덱스를 (email, login_code)
조합 유일 인덱스로 교체한다. 기존 계정은 전부 login_code가 채워져 있어
(9c2b7e1a4f60 백필) 데이터 이관 없이 바로 적용 가능.

Revision ID: d4f6a8c0b2e4
Revises: 9c2b7e1a4f60
Create Date: 2026-09-30 00:00:01.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "d4f6a8c0b2e4"
down_revision: str | None = "9c2b7e1a4f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_email_unique")
        batch.create_index(
            "ix_users_email_login_code_unique", ["email", "login_code"], unique=True
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_email_login_code_unique")
        batch.create_index("ix_users_email_unique", ["email"], unique=True)
