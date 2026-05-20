"""Auth endpoints — login, register, refresh, me."""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import TaxOffice, User
from app.schemas.auth import (
    ChangePasswordRequest,
    CurrentUser,
    LoginRequest,
    ProfileUpdate,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    TokenPair,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _generate_short_code() -> str:
    """6자리 영숫자 인가코드 생성."""
    return secrets.token_hex(3).upper()


def _current_user(user: User, office: TaxOffice | None) -> CurrentUser:
    return CurrentUser(
        id=user.id,
        email=user.email,
        name=user.name,
        tax_office_id=user.tax_office_id,
        is_admin=user.is_admin,
        short_code=office.short_code if office else None,
        office_name=office.name if office else None,
        office_phone=office.phone if office else None,
        office_email=str(office.email) if office and office.email else None,
        office_address=office.address if office else None,
        office_representative=office.representative if office else None,
    )


@router.post("/register", response_model=RegisterResponse)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> RegisterResponse:
    """세무사사무소 회원가입 — 사무소 + 관리자 계정 생성 + 인가코드 자동 발급."""
    # 사업자번호 중복 체크
    existing = (
        await db.execute(
            select(TaxOffice).where(TaxOffice.business_number == payload.business_number)
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 등록된 사업자번호입니다")

    # 인가코드 생성 (중복 방지)
    for _ in range(10):
        short_code = _generate_short_code()
        conflict = (
            await db.execute(
                select(TaxOffice).where(TaxOffice.short_code == short_code)
            )
        ).scalar_one_or_none()
        if not conflict:
            break
    else:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "인가코드 생성 실패")

    # 사무소 생성
    office = TaxOffice(
        name=payload.office_name,
        short_code=short_code,
        business_number=payload.business_number,
        representative=payload.representative,
        phone=payload.phone,
        email=str(payload.email),
        address=payload.address,
    )
    db.add(office)
    await db.flush()

    # 관리자 계정 (아이디 = 사업자번호)
    user = User(
        tax_office_id=office.id,
        email=payload.business_number,
        password_hash=hash_password(payload.password),
        name=payload.representative,
        is_admin=True,
    )
    db.add(user)
    await db.commit()

    # 인가코드 SMS 발송
    try:
        from app.channels.sms import get_sms_channel
        from app.channels.base import MessageRecipient
        sms = get_sms_channel()
        await sms.send(
            MessageRecipient(name=payload.representative, phone=payload.phone),
            body=(
                f"[이지원천] 사무소 인가코드: {short_code}\n"
                f"카카오톡 채널 '이지원천'\n"
                f"http://pf.kakao.com/_lxazsX\n"
                f"채널 가입 및 채팅방 입장 후\n"
                f"인가코드를 다음과 같이 입력하세요\n"
                f"입력할 내용 : 등록 {short_code}"
            ),
        )
    except Exception:
        logger.exception("인가코드 SMS 발송 실패 (가입은 정상 완료)")

    logger.info("사무소 가입 완료: %s (%s) code=%s", payload.office_name, payload.business_number, short_code)

    return RegisterResponse(
        office_id=office.id,
        short_code=short_code,
        access_token=create_access_token(user.id, tax_office_id=office.id),
        refresh_token=create_refresh_token(user.id, tax_office_id=office.id),
    )


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    user = (
        await db.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다")
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
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    office = await db.get(TaxOffice, user.tax_office_id)
    return _current_user(user, office)


@router.patch("/me", response_model=CurrentUser)
async def update_me(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    if payload.name is not None:
        user.name = payload.name
    office = await db.get(TaxOffice, user.tax_office_id)
    if office:
        if payload.office_phone is not None:
            office.phone = payload.office_phone
        if payload.office_email is not None:
            office.email = payload.office_email
        if payload.office_address is not None:
            office.address = payload.office_address
        if payload.office_representative is not None:
            office.representative = payload.office_representative
    await db.commit()
    return _current_user(user, office)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """본인 비밀번호 변경 — 현재 비밀번호 검증 후 교체."""
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "현재 비밀번호가 올바르지 않습니다")
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "새 비밀번호가 기존 비밀번호와 동일합니다")
    user.password_hash = hash_password(payload.new_password)
    await db.commit()
    logger.info("비밀번호 변경 완료: user=%s", user.id)
