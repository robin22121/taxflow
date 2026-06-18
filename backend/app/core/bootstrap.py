"""기동 시 초기 데이터 시드 — 서버 관리자(슈퍼어드민)."""

import logging

from sqlalchemy import select

from app.config import get_settings
from app.core.security import hash_password
from app.db import SessionLocal
from app.models import User

logger = logging.getLogger(__name__)


async def seed_superadmin() -> None:
    """SUPERADMIN_EMAIL/PASSWORD 가 설정돼 있으면 슈퍼어드민 계정을 보장한다.

    - 동일 이메일 계정이 없으면 생성한다.
    - 있으면 비밀번호/슈퍼어드민 플래그를 환경변수 기준으로 동기화한다.
    """
    settings = get_settings()
    email = settings.superadmin_email.strip()
    password = settings.superadmin_password
    if not email or not password:
        return

    async with SessionLocal() as db:
        existing = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing:
            existing.is_superadmin = True
            existing.is_active = True
            existing.password_hash = hash_password(password)
            await db.commit()
            logger.info("슈퍼어드민 계정 동기화: %s", email)
            return

        admin = User(
            tax_office_id=None,
            email=email,
            password_hash=hash_password(password),
            name=settings.superadmin_name,
            is_active=True,
            is_admin=True,
            is_superadmin=True,
        )
        db.add(admin)
        await db.commit()
        logger.info("슈퍼어드민 계정 생성: %s", email)
