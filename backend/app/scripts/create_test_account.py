"""테스트 계정 생성 (거래처 없이 빈 사무소).

실행:
    cd backend && uv run python -m app.scripts.create_test_account
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.security import hash_password
from app.db import SessionLocal
from app.models import TaxOffice, User
from app.models.tax_office import CustomerClass, OfficeApprovalStatus

LOGIN_ID = "1234567890"
PASSWORD = "admin1234!"
OFFICE_NAME = "테스트 세무사사무소"


async def main() -> None:
    async with SessionLocal() as db:
        office = (
            await db.execute(
                select(TaxOffice).where(TaxOffice.business_number == LOGIN_ID)
            )
        ).scalars().first()
        if office is None:
            office = TaxOffice(
                name=OFFICE_NAME,
                short_code="TEST001",
                business_number=LOGIN_ID,
                representative="홍길동",
                phone="010-3640-5642",
                email="robin1q84@gmail.com",
                approval_status=OfficeApprovalStatus.APPROVED,
                approved_at=datetime.now(timezone.utc),
                customer_class=CustomerClass.TRIAL,
            )
            db.add(office)
            await db.flush()
            print(f"새 사무소 생성: {office.name}")
        else:
            print(f"사무소 이미 존재: {office.name}")

        user = (
            await db.execute(select(User).where(User.email == LOGIN_ID))
        ).scalars().first()
        if user is None:
            user = User(
                tax_office_id=office.id,
                email=LOGIN_ID,
                password_hash=hash_password(PASSWORD),
                name="홍길동",
                is_admin=True,
            )
            db.add(user)
            print(f"새 계정 생성: {LOGIN_ID} / {PASSWORD}")
        else:
            user.password_hash = hash_password(PASSWORD)
            user.tax_office_id = office.id
            print(f"계정 갱신: {LOGIN_ID} / {PASSWORD}")

        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
