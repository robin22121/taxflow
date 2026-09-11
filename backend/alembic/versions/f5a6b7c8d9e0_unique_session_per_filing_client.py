"""unique_session_per_filing_client

(monthly_filing_id, client_id)에 유니크 제약 추가.

제약이 없어 동시 요청이 중복 CollectionSession을 만들었고, 2026-09-11 프로덕션에서
중복이 생긴 거래처에 자료요청을 누르자 500이 났다. 신고서에도 같은 직원이 두 번
합산돼 지급총액이 부풀었다. 코드(`get_or_create_session`)는 이미 중복에 내성을
갖췄지만, 애초에 생기지 않게 막는다.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-09-11 00:00:00.000000
"""

from collections.abc import Sequence

from sqlalchemy import inspect as sa_inspect

from alembic import op

revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "uq_collection_sessions_filing_client"


def upgrade() -> None:
    bind = op.get_bind()
    existing = {i["name"] for i in sa_inspect(bind).get_indexes("collection_sessions")}
    if INDEX_NAME not in existing:
        op.create_index(
            INDEX_NAME,
            "collection_sessions",
            ["monthly_filing_id", "client_id"],
            unique=True,
        )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="collection_sessions")
