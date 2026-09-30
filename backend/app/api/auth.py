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
from app.models import OfficeApprovalStatus, TaxOffice, User
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
from app.services.login_lockout import (
    login_locked_until,
    record_login_failure,
    record_login_success,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _generate_short_code() -> str:
    """6자리 영숫자 인가코드 생성."""
    return secrets.token_hex(3).upper()


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

    # 관리자 계정 (아이디 = 사업자번호). 대표 계정은 항상 코드 'a' — 직원은 이후 등록 시 b,c,d… 순차 부여.
    user = User(
        tax_office_id=office.id,
        email=payload.business_number,
        password_hash=hash_password(payload.password),
        name=payload.representative,
        is_admin=True,
        role="OWNER",
        login_code="a",
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

    logger.info("사무소 가입 접수(승인대기): %s (%s) code=%s", payload.office_name, payload.business_number, short_code)

    # 가입 시점에는 토큰을 발급하지 않는다 (가입 후 로그인 화면에서 로그인).
    return RegisterResponse(office_id=office.id, short_code=short_code)


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    # 아이디(사업자번호 등)는 사무소 내 여러 계정이 공유할 수 있다(plan/14 §6.5) — 코드로 구분한다.
    # 코드 생략 시엔 그 아이디에 활성 계정이 정확히 1개일 때만 허용
    # (직원계정이 없는 기존 단일계정 사무소와의 호환. 여러 개면 코드 없이는 어느 계정인지 모호하다).
    query = select(User).where(User.email == payload.email, User.is_active.is_(True))
    if payload.login_code:
        query = query.where(User.login_code == payload.login_code)
    candidates = (await db.execute(query)).scalars().all()
    user = candidates[0] if len(candidates) == 1 else None

    if user:
        locked_until = login_locked_until(user)
        if locked_until:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"로그인 시도가 너무 많습니다. {locked_until.strftime('%H:%M')} 이후 다시 시도해 주세요.",
            )

    if not user or not verify_password(payload.password, user.password_hash):
        if user:
            record_login_failure(user)
            await db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "아이디, 코드 또는 비밀번호가 올바르지 않습니다")

    record_login_success(user)
    await db.commit()

    # 승인 대기 게이트는 해제 — 가입만 하면 로그인 가능. 거부된 사무소만 차단한다.
    if not user.is_superadmin:
        office = await db.get(TaxOffice, user.tax_office_id) if user.tax_office_id else None
        if office and office.approval_status == OfficeApprovalStatus.REJECTED:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "가입이 거부되었습니다. 사무소로 문의해 주세요.")

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
    office = await db.get(TaxOffice, user.tax_office_id) if user.tax_office_id else None
    return CurrentUser(
        id=user.id,
        email=user.email,
        name=user.name,
        tax_office_id=user.tax_office_id,
        is_admin=user.is_admin,
        is_superadmin=user.is_superadmin,
        role=user.role,
        login_code=user.login_code,
        can_write=user.can_write,
        must_change_password=user.must_change_password,
        short_code=office.short_code if office else None,
        office_name=office.name if office else None,
        office_phone=office.phone if office else None,
        office_email=str(office.email) if office and office.email else None,
        office_address=office.address if office else None,
        office_representative=office.representative if office else None,
    )


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """비밀번호 변경 — 최초 로그인 강제 변경(must_change_password)과 자발적 변경 둘 다 사용."""
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "현재 비밀번호가 올바르지 않습니다")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    await db.commit()


@router.patch("/me", response_model=CurrentUser)
async def update_me(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    if payload.name is not None:
        user.name = payload.name
    office = await db.get(TaxOffice, user.tax_office_id) if user.tax_office_id else None
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
    return CurrentUser(
        id=user.id,
        email=user.email,
        name=user.name,
        tax_office_id=user.tax_office_id,
        is_admin=user.is_admin,
        is_superadmin=user.is_superadmin,
        role=user.role,
        login_code=user.login_code,
        can_write=user.can_write,
        must_change_password=user.must_change_password,
        short_code=office.short_code if office else None,
        office_name=office.name if office else None,
        office_phone=office.phone if office else None,
        office_email=str(office.email) if office and office.email else None,
        office_address=office.address if office else None,
        office_representative=office.representative if office else None,
    )
