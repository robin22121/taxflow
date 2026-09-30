"""add_staff_accounts_and_client_assignment

사무소 계정·권한 1단계 (plan/14-accounts-permissions.md §3.2, §4, §6.5).
전부 추가/백필뿐이라 기존 대표 계정 로그인·전 거래처 조회 동작은 그대로다.
로그인 엔드포인트(아이디+코드+비밀번호 3필드화)·스코핑 강제(§5)·직원계정
관리 UI(§6.6)는 이 마이그레이션 범위 밖 — 후속 작업.

- users.role (OWNER/STAFF, is_admin에서 백필)
- users.login_code (사무소 내 개인 코드, 기존 계정은 'a'로 백필. superadmin은 NULL)
- users.can_write (STAFF 쓰기 권한, 전원 true로 백필)
- clients.assigned_user_id (수임담당 배정, NULL=미배정)
- client_assignment_history (배정 이력, append-only)

Revision ID: 9c2b7e1a4f60
Revises: 8a81c4f35548
Create Date: 2026-09-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "9c2b7e1a4f60"
down_revision: str | None = "8a81c4f35548"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("role", sa.String(20), nullable=False, server_default="OWNER"))
        batch.add_column(sa.Column("login_code", sa.String(1), nullable=True))
        batch.add_column(sa.Column("can_write", sa.Boolean(), nullable=False, server_default="1"))

    users = sa.table(
        "users",
        sa.column("id", sa.String),
        sa.column("tax_office_id", sa.String),
        sa.column("is_admin", sa.Boolean),
        sa.column("role", sa.String),
        sa.column("login_code", sa.String),
    )
    conn = op.get_bind()
    # 기존 계정은 전부 사무소 가입 시 생성된 대표 계정 — role은 is_admin 그대로 반영,
    # 사무소 소속(superadmin 제외) 계정만 코드 'a'를 백필한다.
    conn.execute(
        sa.update(users).where(users.c.is_admin.is_(True)).values(role="OWNER")
    )
    conn.execute(
        sa.update(users).where(users.c.is_admin.is_(False)).values(role="STAFF")
    )
    conn.execute(
        sa.update(users)
        .where(users.c.tax_office_id.is_not(None))
        .values(login_code="a")
    )

    with op.batch_alter_table("clients") as batch:
        batch.add_column(sa.Column("assigned_user_id", sa.String(32), nullable=True))
        batch.create_index("ix_clients_assigned_user", ["assigned_user_id"])
        batch.create_foreign_key(
            "fk_clients_assigned_user_id", "users", ["assigned_user_id"], ["id"]
        )

    op.create_table(
        "client_assignment_history",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("client_id", sa.String(32), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("to_user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("changed_by", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_client_assignment_history_client", "client_assignment_history", ["client_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_client_assignment_history_client", table_name="client_assignment_history")
    op.drop_table("client_assignment_history")

    with op.batch_alter_table("clients") as batch:
        batch.drop_constraint("fk_clients_assigned_user_id", type_="foreignkey")
        batch.drop_index("ix_clients_assigned_user")
        batch.drop_column("assigned_user_id")

    with op.batch_alter_table("users") as batch:
        batch.drop_column("can_write")
        batch.drop_column("login_code")
        batch.drop_column("role")
