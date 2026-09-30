"""merge_qa_provider_and_staff_accounts

두 세션이 같은 부모(8a81c4f35548)에서 각자 갈라져 나간 브랜치를 합친다 —
c1e4a7b92f03(다른 세션, PayrollEntry 필요경비·소득구분코드 필드)와
d4f6a8c0b2e4(이 작업, 직원계정·수임담당 배정 + users email/login_code
유니크 교체) 사이에 실제 스키마 변경은 없다.

Revision ID: e5f6a7b8c9d0
Revises: c1e4a7b92f03, d4f6a8c0b2e4
Create Date: 2026-09-30 00:00:02.000000
"""

from collections.abc import Sequence


revision: str = "e5f6a7b8c9d0"
down_revision: str | None = ("c1e4a7b92f03", "d4f6a8c0b2e4")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
