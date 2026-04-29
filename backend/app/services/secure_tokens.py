"""One-time / short-lived token service for sensitive input flows.

Two purposes:
1. Per-client collection request URL (수집 시작) — long TTL (until period closes).
2. Per-employee RRN/입사일 입력 (신규 직원 후속 질문) — short TTL, single-use.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import SecureToken
from app.services.crypto import random_token


class TokenError(ValueError):
    pass


async def issue_token(
    db: AsyncSession,
    *,
    client_id: str,
    purpose: str,
    collection_session_id: str | None = None,
    context: dict[str, Any] | None = None,
    ttl: timedelta = timedelta(days=14),
) -> SecureToken:
    token = SecureToken(
        token=random_token(32),
        client_id=client_id,
        collection_session_id=collection_session_id,
        purpose=purpose,
        context=context or {},
        expires_at=datetime.now(UTC) + ttl,
    )
    db.add(token)
    await db.flush()
    return token


async def get_active_token(db: AsyncSession, token_str: str) -> SecureToken:
    row = (
        await db.execute(select(SecureToken).where(SecureToken.token == token_str))
    ).scalar_one_or_none()
    if not row:
        raise TokenError("토큰을 찾을 수 없습니다")
    if row.used:
        raise TokenError("이미 사용된 토큰입니다")
    if row.expires_at < datetime.now(UTC):
        raise TokenError("만료된 토큰입니다")
    return row


async def consume_token(db: AsyncSession, token: SecureToken) -> None:
    token.used = True
    token.used_at = datetime.now(UTC)
    await db.flush()


def public_url(token: SecureToken) -> str:
    settings = get_settings()
    return f"{settings.app_public_url}/secure/{token.token}"
