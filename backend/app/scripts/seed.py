"""Seed dev DB with one tax office, three clients, and two months of payroll history.

Run::
    uv run python -m app.scripts.seed
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import delete, select

from app.core.security import hash_password
from app.db import SessionLocal
from app.models import (
    Client,
    CollectionEvent,
    CollectionSession,
    Employee,
    EmploymentStatus,
    MonthlyFiling,
    PayrollEntry,
    SecureToken,
    TaxOffice,
    User,
)
from app.models.payroll import IncomeType, MatchStatus
from app.services.crypto import encrypt_rrn, mask_rrn
from app.services.tax_calc import calculate_withholding_tax

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("seed")


async def reset_all(db) -> None:
    for model in [
        PayrollEntry,
        CollectionEvent,
        CollectionSession,
        SecureToken,
        Employee,
        Client,
        MonthlyFiling,
        User,
        TaxOffice,
    ]:
        await db.execute(delete(model))


async def main() -> None:
    async with SessionLocal() as db:
        await reset_all(db)

        office = TaxOffice(name="조명신 세무사사무소", representative="조명신", phone="02-1234-5678")
        db.add(office)
        await db.flush()

        admin = User(
            tax_office_id=office.id,
            email="admin@example.com",
            password_hash=hash_password("admin1234!"),
            name="조명신",
            is_admin=True,
        )
        db.add(admin)

        clients_data = [
            ("(주)에이상사", "111-22-33333", "박대표", "010-1111-2222", "biz-a@example.com"),
            ("비즈테크", "222-33-44444", "이사장", "010-2222-3333", "ops@biztech.local"),
            ("크라프트커피", "333-44-55555", "김사장", "010-3333-4444", None),
        ]
        clients: list[Client] = []
        for name, bn, rep, phone, email in clients_data:
            c = Client(
                tax_office_id=office.id,
                business_name=name,
                business_number=bn,
                representative=rep,
                contact_phone=phone,
                contact_email=email,
            )
            db.add(c)
            clients.append(c)
        await db.flush()

        # Each client gets 3-4 employees
        roster = {
            clients[0].id: [
                ("김연호", "900101-1234567", "E001"),
                ("조명신", "880515-2345678", "E002"),
                ("박민수", "920808-1456789", "E003"),
            ],
            clients[1].id: [
                ("이영수", "850101-1234567", "B001"),
                ("최지원", "910303-2345678", "B002"),
                ("정한별", "950505-1456789", "B003"),
                ("강하늘", "870707-2456789", "B004"),
            ],
            clients[2].id: [
                ("나미경", "930202-2123456", "C001"),
                ("오태호", "890909-1234567", "C002"),
            ],
        }
        employees: dict[str, list[Employee]] = {}
        for client_id, members in roster.items():
            employees[client_id] = []
            for name, rrn, code in members:
                e = Employee(
                    client_id=client_id,
                    name=name,
                    rrn_encrypted=encrypt_rrn(rrn),
                    rrn_last4=rrn.split("-")[1][:4],
                    employee_code=code,
                    hired_at=date(2024, 1, 1),
                    status=EmploymentStatus.ACTIVE,
                )
                db.add(e)
                employees[client_id].append(e)
        await db.flush()

        # 2 months of payroll: 2026-03 (history) and 2026-04 (current, partially filled)
        for period, with_anomaly in [("2026-03", False), ("2026-04", True)]:
            filing = MonthlyFiling(tax_office_id=office.id, period=period)
            db.add(filing)
            await db.flush()
            for client in clients:
                session = CollectionSession(
                    monthly_filing_id=filing.id,
                    client_id=client.id,
                    request_token=f"seed-{period}-{client.id[:8]}",
                )
                db.add(session)
                await db.flush()
                for idx, emp in enumerate(employees[client.id]):
                    base = 2_500_000 + idx * 500_000
                    if with_anomaly and idx == 0 and client == clients[0]:
                        amount = base * 2  # 김연호 anomaly in 2026-04
                        anomaly = {"large_change": {"prev": base, "current": base * 2, "ratio": 2.0}}
                    else:
                        amount = base
                        anomaly = None
                    tax = calculate_withholding_tax(IncomeType.WAGE, amount, dependents=1)
                    db.add(
                        PayrollEntry(
                            monthly_filing_id=filing.id,
                            collection_session_id=session.id,
                            client_id=client.id,
                            employee_id=emp.id,
                            raw_name=emp.name,
                            income_type=IncomeType.WAGE,
                            total_amount=amount,
                            non_taxable=0,
                            taxable=amount,
                            income_tax=tax.income_tax,
                            local_tax=tax.local_tax,
                            payment_date=date(int(period[:4]), int(period[5:]), 25),
                            match_status=MatchStatus.MATCHED,
                            prev_amount=base if with_anomaly else None,
                            anomaly_notes=anomaly,
                            approved=not with_anomaly,
                            dependents=1,
                        )
                    )
            filing.total_clients = len(clients)
            filing.total_entries = sum(len(v) for v in employees.values())

        await db.commit()
        log.info("Seed complete.")
        log.info("  Tax office: %s", office.name)
        log.info("  Login: admin@example.com / admin1234!")
        log.info("  Clients: %d, Employees: %d", len(clients), sum(len(v) for v in employees.values()))


if __name__ == "__main__":
    asyncio.run(main())
