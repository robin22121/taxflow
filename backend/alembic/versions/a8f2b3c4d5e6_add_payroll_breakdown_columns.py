"""add_payroll_breakdown_columns

Splits non_taxable into meal/car/childcare and adds 4대보험 deduction
columns to payroll_entries so the 급여대장 export can be filled with
real values instead of arbitrary distribution.

Revision ID: a8f2b3c4d5e6
Revises: 47d127e07957
Create Date: 2026-05-12 11:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a8f2b3c4d5e6"
down_revision: str | None = "47d127e07957"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_COLUMNS = [
    "meal_amount",
    "car_amount",
    "childcare_amount",
    "national_pension",
    "health_insurance",
    "employment_insurance",
    "longterm_care",
]


def upgrade() -> None:
    for col in _NEW_COLUMNS:
        op.add_column(
            "payroll_entries",
            sa.Column(col, sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    for col in reversed(_NEW_COLUMNS):
        op.drop_column("payroll_entries", col)
