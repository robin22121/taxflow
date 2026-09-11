"""중복 CollectionSession 방지 — 2026-09-11 프로덕션 장애 재현.

(monthly_filing_id, client_id)에 유니크 제약이 없어 동시 요청이 중복 행을 만들었다.
그 거래처에 자료요청을 누르면 `get_or_create_session`이 MultipleResultsFound로
터져 500이 났고, 신고서에는 같은 직원이 두 번 합산돼 지급총액이 부풀었다.

지금은 두 겹으로 막는다.
1. DB 유니크 제약이 중복 행 자체를 거부한다 (f5a6b7c8d9e0)
2. 제약이 아직 없는 DB에서도 `get_or_create_session`이 터지지 않는다
"""

from __future__ import annotations

import pytest


async def _office_client_filing(db):
    from app.models import Client, MonthlyFiling, TaxOffice

    office = TaxOffice(name="중복세션사무소")
    db.add(office)
    await db.flush()
    client = Client(tax_office_id=office.id, business_name="중복세션거래처")
    filing = MonthlyFiling(tax_office_id=office.id, period="2026-05")
    db.add_all([client, filing])
    await db.flush()
    return client, filing


@pytest.mark.asyncio
async def test_duplicate_session_is_rejected_by_db():
    """같은 (신고, 거래처)로 두 번째 세션을 넣으면 DB가 거부한다."""
    from sqlalchemy.exc import IntegrityError

    from app.db import SessionLocal
    from app.models import CollectionSession
    from app.services.invite import get_or_create_session

    async with SessionLocal() as db:
        client, filing = await _office_client_filing(db)
        await get_or_create_session(db, filing, client)

        db.add(
            CollectionSession(
                monthly_filing_id=filing.id,
                client_id=client.id,
                request_token="dup-token-second",
            )
        )
        with pytest.raises(IntegrityError):
            await db.flush()


@pytest.mark.asyncio
async def test_get_or_create_session_reuses_existing():
    """두 번째 호출은 새로 만들지 않고 기존 세션을 돌려준다."""
    from app.db import SessionLocal
    from app.services.invite import get_or_create_session

    async with SessionLocal() as db:
        client, filing = await _office_client_filing(db)
        first = await get_or_create_session(db, filing, client)
        again = await get_or_create_session(db, filing, client)
        assert again.id == first.id
