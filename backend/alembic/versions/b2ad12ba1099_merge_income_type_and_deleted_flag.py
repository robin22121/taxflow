"""merge_income_type_and_deleted_flag

두 세션이 같은 부모(a1b2c3d4e5f6)에서 각자 갈라져 나간 브랜치를 합친다 —
c4d5e6f7a8b9(Employee.income_type 추가, 다른 세션)와 c6d7e8f9a0b1
(PayrollEntry.deleted 추가, 이 작업) 사이에 실제 스키마 변경은 없다.

Revision ID: b2ad12ba1099
Revises: c4d5e6f7a8b9, c6d7e8f9a0b1
Create Date: 2026-09-29 16:31:05.924026
"""

from collections.abc import Sequence


revision: str = "b2ad12ba1099"
down_revision: str | None = ("c4d5e6f7a8b9", "c6d7e8f9a0b1")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
