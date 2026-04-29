"""Auth endpoints — login (password → JWT), refresh, me."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.models import User
from app.schemas.auth import CurrentUser, LoginRequest, RefreshRequest, TokenPair

router = APIRouter()


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    user = (
        await db.execute(select(User).where(User.email == payload.email.lower()))
    ).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return TokenPair(
        access_token=create_access_token(user.id, tax_office_id=user.tax_office_id),
        refresh_token=create_refresh_token(user.id, tax_office_id=user.tax_office_id),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    try:
        decoded = decode_token(payload.refresh_token)
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e
    if decoded.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    user_id = decoded.get("sub")
    user = await db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return TokenPair(
        access_token=create_access_token(user.id, tax_office_id=user.tax_office_id),
        refresh_token=create_refresh_token(user.id, tax_office_id=user.tax_office_id),
    )


@router.get("/me", response_model=CurrentUser)
async def me(user: User = Depends(get_current_user)) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        email=user.email,
        name=user.name,
        tax_office_id=user.tax_office_id,
        is_admin=user.is_admin,
    )
