"""사업주 포털 — 거래처 단위 상설 링크 (plan/12-owner-portal.md §4.3, §5.3).

신고월마다 새 토큰을 쓰던 월간 티켓을 거래처당 하나의 상설 토큰으로 대체한다.
상설 링크는 항상 "지금 열린 신고"로 해석되므로, 옛 링크로 옛 기간 폼에 제출하는
사고가 구조적으로 생기지 않는다. 이미 발송된 세션 링크는 죽지 않도록 함께 해석한다.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.channels import MessageRecipient, get_sms_channel
from app.config import get_settings
from app.core.security import decode_token, hash_password, verify_password
from app.models import (
    Client,
    ClientFilingResult,
    CollectionSession,
    MonthlyFiling,
    MonthlyFilingStatus,
    PayrollEntry,
    SecureToken,
)
from app.services.invite import get_or_create_session
from app.services.secure_tokens import issue_token

logger = logging.getLogger(__name__)

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


async def portal_link_for(db: AsyncSession, client: Client) -> str:
    """거래처에게 보낼 링크. 발송 경로는 모두 이 함수를 거친다 (§3.6).

    세션 토큰 URL을 직접 조립하면 달마다 링크가 바뀌어 옛 링크로 옛 기간 폼에
    제출하는 사고가 난다. 상설 링크는 항상 지금 열린 신고로 해석된다.
    """
    return portal_url(await get_or_issue_portal_token(db, client))


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


# --- PIN 게이트 (§4.3.3) ---------------------------------------------------
#
# PIN은 본인확인이 아니라 민감 구역(직원별 급여액·급여명세서) 열람 통제다.
# 신원은 §4.2대로 세무사에게서 상속받으므로 여기서 다시 확인하지 않는다.

PIN_LENGTH = 6
MAX_PIN_ATTEMPTS = 5
PIN_LOCKOUT = timedelta(hours=24)
# 게이트 통과 상태는 브라우저 세션 한정 — 장기 쿠키를 두지 않는다 (§4.1).
GRANT_TTL = timedelta(hours=2)
_GRANT_TYPE = "portal_grant"


class PinLockedError(Exception):
    """시도 제한에 걸린 상태. ``until``까지 잠긴다."""

    def __init__(self, until: datetime) -> None:
        super().__init__("PIN 입력이 잠겼습니다")
        self.until = until


def generate_pin() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(PIN_LENGTH))


def pin_is_set(client: Client) -> bool:
    return bool(client.portal_pin_hash)


def pin_locked_until(client: Client) -> datetime | None:
    """잠금이 유효하면 해제 시각을, 아니면 None을 돌려준다."""
    until = client.portal_pin_locked_until
    if until is None:
        return None
    if until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    return until if until > datetime.now(UTC) else None


async def set_portal_pin(db: AsyncSession, client: Client) -> str:
    """새 PIN을 발급하고 평문을 1회만 돌려준다. 저장은 해시로만 한다."""
    pin = generate_pin()
    client.portal_pin_hash = hash_password(pin)
    client.portal_pin_failed_count = 0
    client.portal_pin_locked_until = None
    await db.flush()
    return pin


async def verify_portal_pin(db: AsyncSession, client: Client, pin: str) -> bool:
    """PIN을 검증하고 실패 횟수를 갱신한다. 잠금 중이면 PinLockedError."""
    locked = pin_locked_until(client)
    if locked:
        raise PinLockedError(locked)
    if not client.portal_pin_hash:
        return False

    if verify_password(pin, client.portal_pin_hash):
        client.portal_pin_failed_count = 0
        client.portal_pin_locked_until = None
        await db.flush()
        return True

    client.portal_pin_failed_count = (client.portal_pin_failed_count or 0) + 1
    if client.portal_pin_failed_count >= MAX_PIN_ATTEMPTS:
        client.portal_pin_failed_count = 0
        client.portal_pin_locked_until = datetime.now(UTC) + PIN_LOCKOUT
    await db.flush()
    return False


def issue_grant(client_id: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": client_id,
            "type": _GRANT_TYPE,
            "iat": int(now.timestamp()),
            "exp": int((now + GRANT_TTL).timestamp()),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def grant_is_valid(token: str | None, client_id: str) -> bool:
    if not token:
        return False
    try:
        payload = decode_token(token)
    except ValueError:
        return False
    return payload.get("type") == _GRANT_TYPE and payload.get("sub") == client_id


@dataclass
class ArchiveRow:
    """보관함 한 줄 — 사장님이 알고 싶은 건 '얼마 내야 하나'와 '접수증 있나' 둘뿐이다."""

    period: str
    estimated_tax: int
    settled_tax: int | None
    due_date: date | None
    virtual_account: str | None
    epayment_number: str | None
    has_receipt: bool
    has_payment_slip: bool


async def client_archive(db: AsyncSession, client: Client) -> list[ArchiveRow]:
    """거래처의 월별 신고 결과. 최신 기간부터 (§3.1 홈 화면, §3.4 보관함).

    예상 납부세액은 저장하지 않고 ``PayrollEntry``에서 그때그때 합산한다.
    급여를 수정하면 값이 따라 움직여야 하기 때문이다. 홈택스 확정액이
    들어오면 화면이 그쪽을 쓴다.
    """
    sums = (
        await db.execute(
            select(
                MonthlyFiling.period,
                func.sum(PayrollEntry.income_tax + PayrollEntry.local_tax),
            )
            .join(MonthlyFiling, MonthlyFiling.id == PayrollEntry.monthly_filing_id)
            .where(PayrollEntry.client_id == client.id)
            .group_by(MonthlyFiling.period)
        )
    ).all()
    estimated = {period: int(total or 0) for period, total in sums}

    results = (
        await db.execute(
            select(ClientFilingResult).where(ClientFilingResult.client_id == client.id)
        )
    ).scalars().all()
    by_period = {row.period: row for row in results}

    rows: list[ArchiveRow] = []
    for period in sorted(set(estimated) | set(by_period), reverse=True):
        result = by_period.get(period)
        rows.append(
            ArchiveRow(
                period=period,
                estimated_tax=estimated.get(period, 0),
                settled_tax=result.settled_tax if result else None,
                due_date=result.due_date if result else None,
                virtual_account=result.virtual_account if result else None,
                epayment_number=result.epayment_number if result else None,
                has_receipt=bool(result and result.receipt_key),
                has_payment_slip=bool(result and result.payment_slip_key),
            )
        )
    return rows


async def notify_pin_unlock(client: Client) -> None:
    """게이트 통과 시 사장님 번호로 열람 통보 (§4.3.3).

    이 통보가 §4.4 사후 확인 수단의 실체다. 발송 실패가 열람 자체를 막지는 않는다.
    """
    if not client.contact_phone:
        return
    body = (
        f"[이지원천] {client.business_name} 급여 상세가 방금 열람되었습니다. "
        f"본인이 아니라면 담당 세무사에게 알려주세요."
    )
    try:
        await get_sms_channel().send(
            MessageRecipient(
                name=client.business_name,
                phone=client.contact_phone,
                email=client.contact_email,
            ),
            body=body,
        )
    except Exception:
        logger.warning("PIN 열람 통보 실패 client=%s", client.id, exc_info=True)
