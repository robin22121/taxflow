"""새 세무사사무소 + 계정(2798102355)을 만들고 샘플 5개 거래처를 그쪽으로 이동.

- 새 TaxOffice: 이지원천 데모사무소 (business_number=2798102355)
- 새 User: email=2798102355, password=admin1234!, is_admin=True
- 이동 대상 거래처: business_number LIKE '123-45-%' (5개)
- 각 사업자의 monthly_filings(2026-01~07)를 새 사무소로 복제하고
  collection_sessions + payroll_entries를 새 filings로 재연결

실행:
    cd backend && uv run python -m app.scripts.move_samples_to_new_office
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.core.security import hash_password
from app.db import SessionLocal
from app.models import (
    Client,
    CollectionSession,
    MonthlyFiling,
    MonthlyFilingStatus,
    PayrollEntry,
    TaxOffice,
    User,
)
from app.models.tax_office import CustomerClass, OfficeApprovalStatus

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("move_samples")

LOGIN_ID = "2798102355"
PASSWORD = "admin1234!"
OFFICE_NAME = "이지원천 데모사무소"


async def main() -> None:
    async with SessionLocal() as db:
        # ── 1. 이미 있으면 재사용, 없으면 생성 ──
        office = (
            await db.execute(
                select(TaxOffice).where(TaxOffice.business_number == LOGIN_ID)
            )
        ).scalars().first()
        if office is None:
            office = TaxOffice(
                name=OFFICE_NAME,
                short_code="EZOC001",
                business_number=LOGIN_ID,
                representative="홍길동",
                phone="010-3640-5642",
                email="robin1q84@gmail.com",
                approval_status=OfficeApprovalStatus.APPROVED,
                approved_at=datetime.now(timezone.utc),
                customer_class=CustomerClass.REGULAR,
            )
            db.add(office)
            await db.flush()
            log.info("새 세무사사무소 생성: %s (id=%s)", office.name, office.id)
        else:
            log.info("세무사사무소 재사용: %s (id=%s)", office.name, office.id)

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
            log.info("새 계정 생성: 아이디=%s / 비밀번호=%s", LOGIN_ID, PASSWORD)
        else:
            user.password_hash = hash_password(PASSWORD)
            user.tax_office_id = office.id
            log.info("계정 갱신: %s (비밀번호 재설정)", LOGIN_ID)
        await db.flush()

        # ── 2. 이동 대상 5개 사업자 ──
        sample_clients = (
            await db.execute(
                select(Client).where(Client.business_number.like("123-45-%"))
            )
        ).scalars().all()
        log.info("이동 대상 거래처 %d개", len(sample_clients))

        old_office_ids = {c.tax_office_id for c in sample_clients}

        # ── 3. 각 사업자의 payroll_entries가 걸린 monthly_filings 파악 ──
        # (old office 기준)
        sample_client_ids = [c.id for c in sample_clients]
        entries = (
            await db.execute(
                select(PayrollEntry).where(PayrollEntry.client_id.in_(sample_client_ids))
            )
        ).scalars().all()
        involved_filing_ids = {e.monthly_filing_id for e in entries}
        old_filings = (
            await db.execute(
                select(MonthlyFiling).where(MonthlyFiling.id.in_(involved_filing_ids))
            )
        ).scalars().all()
        log.info("연관 monthly_filings %d건 (기간: %s)", len(old_filings),
                 sorted(f.period for f in old_filings))

        # ── 4. 새 사무소용 monthly_filings 만들기 (기간별) ──
        # 새 사무소에 같은 period가 있으면 재사용
        new_filings_by_period: dict[str, MonthlyFiling] = {}
        existing_new = (
            await db.execute(
                select(MonthlyFiling).where(MonthlyFiling.tax_office_id == office.id)
            )
        ).scalars().all()
        for f in existing_new:
            new_filings_by_period[f.period] = f

        for old_f in old_filings:
            if old_f.period in new_filings_by_period:
                continue
            new_f = MonthlyFiling(
                tax_office_id=office.id,
                period=old_f.period,
                status=old_f.status,
            )
            db.add(new_f)
            new_filings_by_period[old_f.period] = new_f
        await db.flush()

        # old_filing_id → new_filing_id 매핑
        old_to_new = {}
        for old_f in old_filings:
            old_to_new[old_f.id] = new_filings_by_period[old_f.period].id

        # ── 5. 거래처 tax_office_id 이동 ──
        for c in sample_clients:
            c.tax_office_id = office.id

        # ── 6. collection_sessions.monthly_filing_id 재연결 ──
        cs_list = (
            await db.execute(
                select(CollectionSession).where(
                    CollectionSession.client_id.in_(sample_client_ids)
                )
            )
        ).scalars().all()
        for cs in cs_list:
            if cs.monthly_filing_id in old_to_new:
                cs.monthly_filing_id = old_to_new[cs.monthly_filing_id]

        # ── 7. payroll_entries.monthly_filing_id 재연결 ──
        for e in entries:
            if e.monthly_filing_id in old_to_new:
                e.monthly_filing_id = old_to_new[e.monthly_filing_id]

        await db.flush()

        # ── 8. 양쪽 사무소의 monthly_filings 캐시 필드 재계산 ──
        # (신규 사무소 + 기존 조명신 사무소 둘 다)
        offices_to_recount = {office.id} | old_office_ids
        for off_id in offices_to_recount:
            filings = (
                await db.execute(
                    select(MonthlyFiling).where(MonthlyFiling.tax_office_id == off_id)
                )
            ).scalars().all()
            for f in filings:
                entry_count = (
                    await db.execute(
                        select(PayrollEntry).where(
                            PayrollEntry.monthly_filing_id == f.id
                        )
                    )
                ).scalars().all()
                f.total_entries = len(entry_count)
                f.total_clients = len({e.client_id for e in entry_count})

        await db.commit()
        log.info("\n완료. 로그인: %s / %s", LOGIN_ID, PASSWORD)


if __name__ == "__main__":
    asyncio.run(main())
