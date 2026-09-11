"""중복 CollectionSession 내성 — 2026-09-11 프로덕션 장애 재현.

(monthly_filing_id, client_id)에 유니크 제약이 없어 동시 요청이 중복 행을 만든다.
프로덕션에서 이 상태의 거래처에 자료요청을 누르면 `get_or_create_session`이
`MultipleResultsFound`로 터져 500이 났다.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_get_or_create_session_tolerates_duplicates():
    """중복 행이 있어도 터지지 않고 가장 먼저 만들어진 세션을 돌려준다."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Client, CollectionSession, MonthlyFiling, TaxOffice
    from app.services.invite import get_or_create_session

    async with SessionLocal() as db:
        office = TaxOffice(name="중복세션사무소")
        db.add(office)
        await db.flush()
        client = Client(tax_office_id=office.id, business_name="중복세션거래처")
        filing = MonthlyFiling(tax_office_id=office.id, period="2026-05")
        db.add_all([client, filing])
        await db.flush()

        first = await get_or_create_session(db, filing, client)
        # 동시 요청이 만든 두 번째 행을 그대로 재현한다.
        db.add(
            CollectionSession(
                monthly_filing_id=filing.id,
                client_id=client.id,
                request_token="dup-token-second",
            )
        )
        await db.flush()

        rows = (
            await db.execute(
                select(CollectionSession).where(
                    CollectionSession.monthly_filing_id == filing.id,
                    CollectionSession.client_id == client.id,
                )
            )
        ).scalars().all()
        assert len(rows) == 2

        again = await get_or_create_session(db, filing, client)
        assert again.id == first.id
