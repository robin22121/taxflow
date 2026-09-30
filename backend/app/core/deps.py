"""FastAPI dependencies — current user, DB session."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db import SessionLocal
from app.models import Client, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=True)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_token(token)
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e

    if payload.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")

    user_id = payload.get("sub")
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


async def require_same_office(user: User, tax_office_id: str) -> None:
    if user.tax_office_id != tax_office_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-office access denied")


async def require_superadmin(user: User = Depends(get_current_user)) -> User:
    """서버 관리자 전용 엔드포인트 가드."""
    if not user.is_superadmin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "서버 관리자 권한이 필요합니다")
    return user


async def require_owner(user: User = Depends(get_current_user)) -> User:
    """사무소 대표(OWNER) 전용 엔드포인트 가드 — 직원계정 관리·수임담당 배정 등
    (plan/14-accounts-permissions.md §3). superadmin은 사무소 소속이 아니므로 통과 대상 아님."""
    if user.role != "OWNER":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "대표(세무사) 계정만 가능합니다")
    return user


def visible_clients(user: User) -> Select:
    """user가 볼 수 있는 거래처 select. 목록·집계 쿼리는 전부 이것에서 출발한다
    (plan/14-accounts-permissions.md §5.1). STAFF는 자기 담당 거래처만, OWNER는
    사무소 전체(미배정 포함)."""
    q = select(Client).where(Client.tax_office_id == user.tax_office_id)
    if user.role == "STAFF":
        q = q.where(Client.assigned_user_id == user.id)
    return q


async def get_scoped_client(
    client_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Client:
    """거래처 단건 의존성 — 사무소 불일치·담당 아님 모두 404
    (남의 거래처 ID의 존재 여부 자체를 노출하지 않는다, §5.1)."""
    client = (await db.execute(visible_clients(user).where(Client.id == client_id))).scalar_one_or_none()
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return client


async def require_write(user: User = Depends(get_current_user)) -> User:
    """읽기전용 STAFF의 쓰기 계열 엔드포인트 차단 (plan/14 §3.2 can_write)."""
    if user.role == "STAFF" and not user.can_write:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "읽기 전용 계정입니다")
    return user
