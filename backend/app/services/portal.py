"""사업주 포털 — 거래처 단위 상설 링크 (plan/12-owner-portal.md §4.3, §5.3).

신고월마다 새 토큰을 쓰던 월간 티켓을 거래처당 하나의 상설 토큰으로 대체한다.
상설 링크는 항상 "지금 열린 신고"로 해석되므로, 옛 링크로 옛 기간 폼에 제출하는
사고가 구조적으로 생기지 않는다. 이미 발송된 세션 링크는 죽지 않도록 함께 해석한다.
"""

from __future__ import annotations

import enum
import logging
import re
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
    Employee,
    EmploymentStatus,
    MonthlyFiling,
    MonthlyFilingStatus,
    PayrollEntry,
    SecureToken,
)
from app.models.payroll import IncomeType
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
_PIN_RE = re.compile(r"[0-9]{6}")
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


class InvalidPinError(ValueError):
    """세무사가 지정한 PIN이 형식에 맞지 않는다."""


def validate_pin(pin: str) -> str:
    """지정 PIN 검증 — ASCII 숫자 6자리만 받는다.

    ``str.isdigit()`` 은 전각 숫자('１２３４５６')도 참이라 쓰지 않는다. 전각으로 저장되면
    사장님이 반각으로 입력했을 때 영영 열리지 않는 PIN이 된다.
    """
    cleaned = pin.strip()
    if not _PIN_RE.fullmatch(cleaned):
        raise InvalidPinError(f"PIN은 숫자 {PIN_LENGTH}자리여야 합니다")
    return cleaned


async def set_portal_pin(db: AsyncSession, client: Client, pin: str | None = None) -> str:
    """PIN을 설정하고 평문을 1회만 돌려준다. 저장은 해시로만 한다.

    ``pin`` 을 주면 세무사가 지정한 값을, 없으면 무작위로 만든다.
    """
    pin = validate_pin(pin) if pin is not None else generate_pin()
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


# --- §8 리디자인 — 5-단계 상태·지난달 요약·월별 인건비·직원 상세 --------------

class PortalStatus(str, enum.Enum):
    """사장님 화면에 보이는 5-단계 상태 (plan §8.7 신호등)."""

    NONE = "NONE"              # 지금 열린 신고 없음
    COLLECTING = "COLLECTING"  # 자료 수집 중
    REVIEWING = "REVIEWING"    # 검토 대기
    FILED = "FILED"            # 신고 완료·납부 대기
    PAID = "PAID"              # 납부 완료·확정
    OVERDUE = "OVERDUE"        # 미납·기한 초과


# MonthlyFiling.status → PortalStatus. MonthlyFiling은 사무소 단위이므로
# 거래처별 "납부 완료"는 이 매핑만으로는 나오지 않는다 — settled_tax + due_date로 보정한다.
_FILING_TO_PORTAL: dict[MonthlyFilingStatus, PortalStatus] = {
    MonthlyFilingStatus.DRAFT: PortalStatus.COLLECTING,
    MonthlyFilingStatus.COLLECTING: PortalStatus.COLLECTING,
    MonthlyFilingStatus.REVIEWING: PortalStatus.REVIEWING,
    MonthlyFilingStatus.APPROVED: PortalStatus.FILED,
    MonthlyFilingStatus.EXCEL_GENERATED: PortalStatus.FILED,
    MonthlyFilingStatus.FILED: PortalStatus.FILED,
    MonthlyFilingStatus.COMPLETED: PortalStatus.PAID,
}


def previous_period(period: str) -> str:
    """"2026-09" → "2026-08". 1월은 전년 12월로 넘어간다."""
    y, m = period.split("-")
    year, month = int(y), int(m)
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


async def _filing_result(
    db: AsyncSession, client_id: str, period: str
) -> ClientFilingResult | None:
    return (
        await db.execute(
            select(ClientFilingResult).where(
                ClientFilingResult.client_id == client_id,
                ClientFilingResult.period == period,
            )
        )
    ).scalar_one_or_none()


async def _estimated_tax(db: AsyncSession, client_id: str, period: str) -> int:
    total = (
        await db.execute(
            select(func.sum(PayrollEntry.income_tax + PayrollEntry.local_tax))
            .join(MonthlyFiling, MonthlyFiling.id == PayrollEntry.monthly_filing_id)
            .where(
                PayrollEntry.client_id == client_id,
                MonthlyFiling.period == period,
            )
        )
    ).scalar()
    return int(total or 0)


@dataclass
class PortalStatusInfo:
    """상태 스트립·납부 카드 공용 뷰."""

    state: PortalStatus
    period: str | None
    due_date: date | None
    estimated_tax: int
    settled_tax: int | None
    virtual_account: str | None
    epayment_number: str | None
    has_receipt: bool
    has_payment_slip: bool
    tax_office_name: str


async def derive_status(
    db: AsyncSession, client: Client, filing: MonthlyFiling | None
) -> PortalStatusInfo:
    """열린 신고 + 결과 레코드로 5-단계 상태를 결정한다."""
    # ``client.tax_office`` 는 lazy — async 컨텍스트에서 건드리면 MissingGreenlet.
    # 언제나 명시적으로 fetch 한다.
    from app.models.tax_office import TaxOffice

    tax_office_name = ""
    if client.tax_office_id:
        office = await db.get(TaxOffice, client.tax_office_id)
        if office:
            tax_office_name = office.name

    if filing is None:
        return PortalStatusInfo(
            state=PortalStatus.NONE,
            period=None,
            due_date=None,
            estimated_tax=0,
            settled_tax=None,
            virtual_account=None,
            epayment_number=None,
            has_receipt=False,
            has_payment_slip=False,
            tax_office_name=tax_office_name,
        )

    result = await _filing_result(db, client.id, filing.period)
    estimated = await _estimated_tax(db, client.id, filing.period)

    base_state = _FILING_TO_PORTAL.get(filing.status, PortalStatus.COLLECTING)
    due_date = result.due_date if result else None
    # 미납 판정: FILED 상태에서 due_date가 지났으면 OVERDUE.
    # COMPLETED(납부완료)면 지나도 문제 없음.
    state = base_state
    if (
        base_state == PortalStatus.FILED
        and due_date is not None
        and date.today() > due_date
    ):
        state = PortalStatus.OVERDUE

    return PortalStatusInfo(
        state=state,
        period=filing.period,
        due_date=due_date,
        estimated_tax=estimated,
        settled_tax=result.settled_tax if result else None,
        virtual_account=result.virtual_account if result else None,
        epayment_number=result.epayment_number if result else None,
        has_receipt=bool(result and result.receipt_key),
        has_payment_slip=bool(result and result.payment_slip_key),
        tax_office_name=tax_office_name,
    )


@dataclass
class LastMonthEntry:
    name: str
    income_type: str
    total_amount: int


@dataclass
class LastMonthSummary:
    """지난달 명세 — 요약은 항상 보이고, 개별 entries는 gated=True일 때만 담긴다."""

    period: str | None
    employee_count: int
    total_amount: int
    total_tax: int
    net_amount: int
    entries: list[LastMonthEntry] | None


async def last_month_summary(
    db: AsyncSession,
    client: Client,
    current_period: str | None,
    *,
    gated: bool,
) -> LastMonthSummary:
    """지난달 지급명세 (plan §8.3 "지난달 지급명세" 카드).

    금액 합계는 게이트 앞에서도 보이지만, 직원별 명세는 게이트 뒤 (§4.3.1 전월 프리필).
    """
    if current_period is None:
        return LastMonthSummary(None, 0, 0, 0, 0, None if not gated else [])

    prev = previous_period(current_period)
    entries = (
        await db.execute(
            select(PayrollEntry)
            .join(MonthlyFiling, MonthlyFiling.id == PayrollEntry.monthly_filing_id)
            .where(
                PayrollEntry.client_id == client.id,
                MonthlyFiling.period == prev,
            )
            .order_by(PayrollEntry.raw_name)
        )
    ).scalars().all()

    total_amount = sum(e.total_amount for e in entries)
    total_tax = sum((e.income_tax or 0) + (e.local_tax or 0) for e in entries)
    return LastMonthSummary(
        period=prev,
        employee_count=len({e.raw_name for e in entries}),
        total_amount=int(total_amount),
        total_tax=int(total_tax),
        net_amount=int(total_amount - total_tax),
        entries=(
            [
                LastMonthEntry(
                    name=e.raw_name,
                    income_type=e.income_type.value,
                    total_amount=int(e.total_amount),
                )
                for e in entries
            ]
            if gated
            else None
        ),
    )


@dataclass
class MonthlyCostPoint:
    period: str
    wage: int         # 근로소득
    business: int     # 사업소득
    daily: int        # 일용근로
    other: int        # 기타·퇴직
    total: int


@dataclass
class MonthlyCostReport:
    kpis: dict[str, int | float | None]
    series: list[MonthlyCostPoint]


_ALLOWED_MONTHS = (3, 6, 12, 24)


async def monthly_cost_series(
    db: AsyncSession, client: Client, months: int
) -> MonthlyCostReport:
    """최근 N개월의 소득종류별 인건비 (plan §8.5).

    - 시리즈: 월별로 근로/사업/일용/기타 4개 스택 값
    - KPI: N개월 총·월평균·YoY(같은 달 전년 대비)
    """
    if months not in _ALLOWED_MONTHS:
        raise ValueError(f"months must be one of {_ALLOWED_MONTHS}")

    # 최신 N + 12(YoY 계산용) 개월만 뽑는다. 데이터가 없으면 그만큼 비어 있음.
    today = date.today()
    year, month = today.year, today.month
    lookback = months + 12
    periods: list[str] = []
    for _ in range(lookback):
        periods.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    rows = (
        await db.execute(
            select(
                MonthlyFiling.period,
                PayrollEntry.income_type,
                func.sum(PayrollEntry.total_amount),
            )
            .join(MonthlyFiling, MonthlyFiling.id == PayrollEntry.monthly_filing_id)
            .where(
                PayrollEntry.client_id == client.id,
                MonthlyFiling.period.in_(periods),
            )
            .group_by(MonthlyFiling.period, PayrollEntry.income_type)
        )
    ).all()

    by_period: dict[str, dict[IncomeType, int]] = {p: {} for p in periods}
    for period, income_type, total in rows:
        by_period[period][income_type] = int(total or 0)

    def _point(period: str) -> MonthlyCostPoint:
        bucket = by_period.get(period, {})
        wage = bucket.get(IncomeType.WAGE, 0)
        business = bucket.get(IncomeType.BUSINESS, 0)
        daily = bucket.get(IncomeType.DAILY, 0)
        other = bucket.get(IncomeType.OTHER, 0) + bucket.get(IncomeType.RETIREMENT, 0)
        return MonthlyCostPoint(
            period=period,
            wage=wage,
            business=business,
            daily=daily,
            other=other,
            total=wage + business + daily + other,
        )

    # 최신이 뒤로 가는 게 차트에 자연스럽다.
    window = list(reversed(periods[:months]))
    series = [_point(p) for p in window]

    total_n = sum(p.total for p in series)
    non_zero = sum(1 for p in series if p.total > 0)
    monthly_avg = int(total_n / non_zero) if non_zero else 0

    # YoY: 최신 달과 12개월 전 같은 달 비교
    latest = series[-1] if series else None
    yoy: float | None = None
    if latest and latest.total > 0:
        prev_year_period = f"{int(latest.period[:4]) - 1:04d}-{latest.period[5:7]}"
        prev_point = _point(prev_year_period)
        if prev_point.total > 0:
            yoy = round((latest.total - prev_point.total) / prev_point.total * 100, 1)

    return MonthlyCostReport(
        kpis={
            "total": total_n,
            "monthly_avg": monthly_avg,
            "yoy_pct": yoy,
        },
        series=series,
    )


@dataclass
class EmployeeHistoryRow:
    period: str
    total_amount: int
    tax: int
    net_amount: int


@dataclass
class EmployeeDetail:
    id: str
    name: str
    position: str | None
    department: str | None
    hired_at: date | None
    resigned_at: date | None
    status: str
    income_type: str | None       # 최근 급여의 소득종류
    total_ytd: int | None         # gated only
    monthly_avg: int | None       # gated only
    tax_ytd: int | None           # gated only
    history: list[EmployeeHistoryRow] | None  # gated only


async def employee_detail(
    db: AsyncSession, client: Client, employee_id: str, *, gated: bool
) -> EmployeeDetail | None:
    """직원 카드 상세 (plan §8.6).

    이름·직위·부서·입사일은 게이트 앞. 급여 이력·KPI는 PIN 게이트 뒤.
    """
    emp = await db.get(Employee, employee_id)
    if not emp or emp.client_id != client.id:
        return None

    # 최근 급여로부터 소득종류 힌트
    latest_entry = (
        await db.execute(
            select(PayrollEntry)
            .where(
                PayrollEntry.client_id == client.id,
                PayrollEntry.employee_id == emp.id,
            )
            .order_by(PayrollEntry.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    income_type = latest_entry.income_type.value if latest_entry else None

    total_ytd: int | None = None
    monthly_avg: int | None = None
    tax_ytd: int | None = None
    history: list[EmployeeHistoryRow] | None = None

    if gated:
        this_year = f"{date.today().year:04d}"
        entries = (
            await db.execute(
                select(MonthlyFiling.period, PayrollEntry)
                .join(MonthlyFiling, MonthlyFiling.id == PayrollEntry.monthly_filing_id)
                .where(
                    PayrollEntry.client_id == client.id,
                    PayrollEntry.employee_id == emp.id,
                    MonthlyFiling.period.like(f"{this_year}-%"),
                )
                .order_by(MonthlyFiling.period.desc())
            )
        ).all()
        rows = [
            EmployeeHistoryRow(
                period=period,
                total_amount=int(entry.total_amount),
                tax=int((entry.income_tax or 0) + (entry.local_tax or 0)),
                net_amount=int(
                    entry.total_amount
                    - (entry.income_tax or 0)
                    - (entry.local_tax or 0)
                ),
            )
            for period, entry in entries
        ]
        history = rows
        total_ytd = sum(r.total_amount for r in rows)
        tax_ytd = sum(r.tax for r in rows)
        monthly_avg = int(total_ytd / len(rows)) if rows else 0

    return EmployeeDetail(
        id=emp.id,
        name=emp.name,
        position=emp.position,
        department=emp.department,
        hired_at=emp.hired_at,
        resigned_at=emp.resigned_at,
        status=emp.status.value,
        income_type=income_type,
        total_ytd=total_ytd,
        monthly_avg=monthly_avg,
        tax_ytd=tax_ytd,
        history=history,
    )


async def list_employees(
    db: AsyncSession,
    client: Client,
    *,
    include_resigned: bool,
) -> list[Employee]:
    """포털 직원 리스트 (plan §8.6).

    ``portal_employees`` 경로의 확장판 — 퇴사자도 함께 볼 수 있게 한다.
    """
    stmt = select(Employee).where(Employee.client_id == client.id)
    if not include_resigned:
        stmt = stmt.where(Employee.status == EmploymentStatus.ACTIVE)
    return list(
        (await db.execute(stmt.order_by(Employee.name))).scalars().all()
    )


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
