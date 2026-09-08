"""add_wehago_payroll_columns

위하고T 급여대장 실측 양식((임시)주식회사 동문-202511.xlsx)에 있으나
모델에 대응 필드가 없어 0/공란으로만 나가던 항목을 추가한다.

- payroll_entries: 학자금상환액 / 정산보험료 / 월세지원금 (공제 R·S·T열)
- employees: 부서 / 직급 / 직종 (급여대장 C·D·E열)

Revision ID: a9b0c1d2e3f4
Revises: f7a8b9c0d1e2
Create Date: 2026-09-08 10:30:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a9b0c1d2e3f4"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DEDUCTION_COLUMNS = [
    "student_loan",           # 학자금상환액
    "settlement_insurance",   # 정산보험료 (건강보험 연말정산분 등)
    "rent_support",           # 월세지원금
]

_EMPLOYEE_COLUMNS = [
    "department",  # 부서
    "position",    # 직급
    "job_type",    # 직종
]


def upgrade() -> None:
    for col in _DEDUCTION_COLUMNS:
        op.add_column(
            "payroll_entries",
            sa.Column(col, sa.Integer(), nullable=False, server_default="0"),
        )
    for col in _EMPLOYEE_COLUMNS:
        op.add_column(
            "employees",
            sa.Column(col, sa.String(length=50), nullable=True),
        )


def downgrade() -> None:
    for col in reversed(_EMPLOYEE_COLUMNS):
        op.drop_column("employees", col)
    for col in reversed(_DEDUCTION_COLUMNS):
        op.drop_column("payroll_entries", col)
