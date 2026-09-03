"""특정 세무사사무소의 모든 거래처에 대해 급여내역·고객소통내역을 초기화.

거래처(Client)·직원(Employee) 마스터 레코드는 보존하고,
급여내역(PayrollEntry)·소통세션(CollectionSession)·소통이벤트(CollectionEvent)만 삭제한다.

서버 셸에서 실행::

    # 1) 먼저 dry-run으로 삭제 대상 건수만 확인 (실제 삭제 안 함)
    python -m app.scripts.reset_office_data 2798102355 11F878

    # 2) 확인 후 실제 삭제
    python -m app.scripts.reset_office_data 2798102355 11F878 --yes

인자: [business_number] [short_code] [--yes]
  business_number 또는 short_code(인가코드) 중 하나라도 일치하는 사무소가 대상.
  --yes 없으면 dry-run (건수만 출력, 커밋 안 함).
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.models import (
    Client,
    CollectionEvent,
    CollectionSession,
    Employee,
    PayrollEntry,
    SecureToken,
    TaxOffice,
)


async def main(business_number: str, short_code: str, commit: bool) -> None:
    async with SessionLocal() as db:
        bn_variants = {business_number, business_number.replace("-", "")}
        offices = (
            await db.execute(
                select(TaxOffice).where(
                    (TaxOffice.business_number.in_(bn_variants))
                    | (TaxOffice.short_code == short_code)
                )
            )
        ).scalars().all()

        if not offices:
            print(f"[!] 사무소를 찾지 못했습니다. business_number={business_number!r} short_code={short_code!r}")
            return

        if len(offices) > 1:
            print(f"[!] 사무소가 {len(offices)}개 매칭됨 — 의도치 않은 대상 방지를 위해 중단합니다:")
            for o in offices:
                print(f"    id={o.id} name={o.name!r} short_code={o.short_code!r} biz={o.business_number!r}")
            print("    business_number/short_code를 더 정확히 지정해 한 곳만 매칭되게 하세요.")
            return

        office = offices[0]
        print(f"대상 사무소: {office.name!r} (id={office.id}, short_code={office.short_code!r}, biz={office.business_number!r})")

        client_ids = (
            await db.execute(select(Client.id).where(Client.tax_office_id == office.id))
        ).scalars().all()
        print(f"거래처 수: {len(client_ids)}")
        if not client_ids:
            print("거래처가 없어 초기화할 데이터가 없습니다.")
            return

        sess_ids = (
            await db.execute(
                select(CollectionSession.id).where(CollectionSession.client_id.in_(client_ids))
            )
        ).scalars().all()

        async def count(model, whereclause) -> int:
            return (await db.execute(select(func.count()).select_from(model).where(whereclause))).scalar_one()

        pay_n = await count(PayrollEntry, PayrollEntry.client_id.in_(client_ids))
        ev_n = await count(CollectionEvent, CollectionEvent.session_id.in_(sess_ids)) if sess_ids else 0
        sess_n = len(sess_ids)
        tok_n = await count(SecureToken, SecureToken.client_id.in_(client_ids))
        emp_n = await count(Employee, Employee.client_id.in_(client_ids))

        print("─" * 50)
        print(f"삭제 예정 급여내역(payroll_entries)    : {pay_n}")
        print(f"삭제 예정 소통이벤트(collection_events) : {ev_n}")
        print(f"삭제 예정 소통세션(collection_sessions) : {sess_n}")
        print(f"삭제 예정 입력토큰(secure_tokens)       : {tok_n}")
        print(f"보존되는 직원(employees)               : {emp_n}")
        print(f"보존되는 거래처(clients)               : {len(client_ids)}")
        print("─" * 50)

        if not commit:
            print("[DRY-RUN] 실제 삭제하지 않았습니다. 위 건수가 맞으면 끝에 --yes 를 붙여 다시 실행하세요.")
            return

        # FK 의존성 순서: payroll → secure_tokens → collection_events → collection_sessions
        # (payroll·secure_tokens 모두 collection_sessions 를 참조하므로 세션보다 먼저 삭제)
        await db.execute(delete(PayrollEntry).where(PayrollEntry.client_id.in_(client_ids)))
        await db.execute(delete(SecureToken).where(SecureToken.client_id.in_(client_ids)))
        if sess_ids:
            await db.execute(delete(CollectionEvent).where(CollectionEvent.session_id.in_(sess_ids)))
        await db.execute(delete(CollectionSession).where(CollectionSession.client_id.in_(client_ids)))
        await db.commit()

        print("[완료] 급여내역·소통내역을 초기화했습니다. (거래처·직원 보존)")


if __name__ == "__main__":
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    commit = "--yes" in sys.argv[1:]
    bn = pos[0] if len(pos) > 0 else "2798102355"
    sc = pos[1] if len(pos) > 1 else "11F878"
    asyncio.run(main(bn, sc, commit))
