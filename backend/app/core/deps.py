"""FastAPI dependencies — current user, DB session."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db import SessionLocal
from app.models import User

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
