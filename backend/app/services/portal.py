"""사업주 포털 — 거래처 단위 상설 링크 (plan/12-owner-portal.md §4.3, §5.3).

신고월마다 새 토큰을 쓰던 월간 티켓을 거래처당 하나의 상설 토큰으로 대체한다.
상설 링크는 항상 "지금 열린 신고"로 해석되므로, 옛 링크로 옛 기간 폼에 제출하는
사고가 구조적으로 생기지 않는다. 이미 발송된 세션 링크는 죽지 않도록 함께 해석한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models import (
    Client,
    CollectionSession,
    MonthlyFiling,
    MonthlyFilingStatus,
    SecureToken,
)
from app.services.invite import get_or_create_session
from app.services.secure_tokens import issue_token

PORTAL_PURPOSE = "CLIENT_PORTAL"

# 상설 링크는 만료가 아니라 재발급(rotate)으로 회수한다 (§4.3.1).
# expires_at이 NOT NULL이라 먼 미래값을 넣어 사실상 만료를 끈다.
_PORTAL_TTL = timedelta(days=36_500)

# 자료를 아직 받을 수 있는 신고 상태. app/api/clients.py의 _ACTIVE_FILING_STATUSES와
# 같은 기준이다 — 제출·완료된 신고에 늦게 온 자료가 조용히 섞이면 안 된다.
OPEN_FILING_STATUSES = (
    MonthlyFilingStatus.DRAFT,
    MonthlyFilingStatus.COLLECTING,
    MonthlyFilingStatus.REVIEWING,
)


@dataclass
class ResolvedLink:
    """공개 링크 해석 결과. ``filing``이 None이면 지금 받을 수 있는 신고가 없다."""

    client: Client
    filing: MonthlyFiling | None
    session: CollectionSession | None


def _is_expired(token: SecureToken) -> bool:
    # SQLite는 timezone-aware 컬럼도 naive datetime으로 돌려준다.
    expires = token.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires < datetime.now(UTC)


async def _active_portal_tokens(db: AsyncSession, client_id: str) -> list[SecureToken]:
    rows = (
        await db.execute(
            select(SecureToken)
            .where(
                SecureToken.client_id == client_id,
                SecureToken.purpose == PORTAL_PURPOSE,
                SecureToken.used.is_(False),
            )
            .order_by(SecureToken.created_at.desc())
        )
    ).scalars().all()
    return [row for row in rows if not _is_expired(row)]


async def get_or_issue_portal_token(db: AsyncSession, client: Client) -> SecureToken:
    """거래처의 상설 토큰을 반환하고, 없으면 발급한다. 거래처당 활성 토큰 1개."""
    active = await _active_portal_tokens(db, client.id)
    if active:
        return active[0]
    return await issue_token(
        db, client_id=client.id, purpose=PORTAL_PURPOSE, ttl=_PORTAL_TTL
    )


async def rotate_portal_token(db: AsyncSession, client: Client) -> SecureToken:
    """기존 링크를 즉시 죽이고 새 링크를 발급한다 (§4.5 강제 무효화)."""
    now = datetime.now(UTC)
    for token in await _active_portal_tokens(db, client.id):
        token.used = True
        token.used_at = now
    await db.flush()
    return await issue_token(
        db, client_id=client.id, purpose=PORTAL_PURPOSE, ttl=_PORTAL_TTL
    )


def portal_url(token: SecureToken) -> str:
    return f"{get_settings().app_public_url}/r/{token.token}"


async def current_open_filing(db: AsyncSession, client: Client) -> MonthlyFiling | None:
    """거래처가 속한 사무소에서 지금 자료를 받고 있는 신고 중 가장 최근 기간."""
    return (
        await db.execute(
            select(MonthlyFiling)
            .where(
                MonthlyFiling.tax_office_id == client.tax_office_id,
                MonthlyFiling.status.in_(OPEN_FILING_STATUSES),
            )
            .order_by(MonthlyFiling.period.desc())
        )
    ).scalars().first()


async def resolve_public_link(
    db: AsyncSession, token_str: str, *, create_session: bool
) -> ResolvedLink | None:
    """공개 토큰을 해석한다. 상설 링크와 구 세션 링크를 모두 받는다.

    ``create_session``은 제출 경로에서만 True — 단순 조회(GET)가 세션을 만들지 않도록.
    """
    session = (
        await db.execute(
            select(CollectionSession)
            .where(CollectionSession.request_token == token_str)
            .options(
                selectinload(CollectionSession.client),
                selectinload(CollectionSession.monthly_filing),
            )
        )
    ).scalar_one_or_none()
    if session:
        return ResolvedLink(
            client=session.client, filing=session.monthly_filing, session=session
        )

    token = (
        await db.execute(
            select(SecureToken)
            .where(
                SecureToken.token == token_str,
                SecureToken.purpose == PORTAL_PURPOSE,
            )
            .options(selectinload(SecureToken.client))
        )
    ).scalar_one_or_none()
    if not token or token.used or _is_expired(token):
        return None

    client = token.client
    filing = await current_open_filing(db, client)
    if filing is None:
        return ResolvedLink(client=client, filing=None, session=None)

    if create_session:
        open_session = await get_or_create_session(db, filing, client)
    else:
        open_session = (
            await db.execute(
                select(CollectionSession).where(
                    CollectionSession.monthly_filing_id == filing.id,
                    CollectionSession.client_id == client.id,
                )
            )
        ).scalar_one_or_none()
    return ResolvedLink(client=client, filing=filing, session=open_session)
