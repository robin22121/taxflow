"""로그인 시도 제한 — 사업주 포털 PIN 잠금(services/portal.py)과 같은 패턴.

plan/14-accounts-permissions.md §8 "일정 횟수 인증 실패 시 접근 제한".
"""

from datetime import UTC, datetime, timedelta

from app.models import User

MAX_LOGIN_ATTEMPTS = 5
# 포털 PIN(고객용, 24시간)보다 짧게 — 매일 로그인하는 직원 계정이 잠기면
# 업무가 그 시간만큼 바로 멈추므로 지나치게 길게 잡지 않는다.
LOGIN_LOCKOUT = timedelta(minutes=30)


def login_locked_until(user: User) -> datetime | None:
    """잠금이 유효하면 해제 시각을, 아니면 None을 돌려준다."""
    until = user.locked_until
    if until is None:
        return None
    if until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    return until if until > datetime.now(UTC) else None


def record_login_success(user: User) -> None:
    user.failed_login_count = 0
    user.locked_until = None


def record_login_failure(user: User) -> None:
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if user.failed_login_count >= MAX_LOGIN_ATTEMPTS:
        user.failed_login_count = 0
        user.locked_until = datetime.now(UTC) + LOGIN_LOCKOUT
