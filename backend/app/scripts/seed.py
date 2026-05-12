"""Seed dev DB with realistic sample data for full pipeline verification.

Covers 8 scenarios:
  1. Normal match (same amount as prev month)
  2. Salary increase (≥1.5x → anomaly flag)
  3. Salary decrease (≤0.5x → anomaly flag)
  4. New hire (employee exists but no prev payroll)
  5. Resignation (paid prev month, absent this month)
  6. Business income (BUSINESS, 3.3% withholding)
  7. Daily worker (DAILY)
  8. Non-taxable included (식대 200,000)

Run::
    uv run python -m app.scripts.seed
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import delete

from app.core.security import hash_password
from app.db import SessionLocal
from app.models import (
    BUSINESS_TYPE_CODES,
    BusinessTypeCode,
    Client,
    CollectionEvent,
    CollectionSession,
    CollectionSessionStatus,
    Employee,
    EmploymentStatus,
    MonthlyFiling,
    MonthlyFilingStatus,
    PayrollEntry,
    SecureToken,
    TaxOffice,
    User,
)
from app.models.payroll import IncomeType, MatchStatus
from app.services.crypto import encrypt_rrn
from app.services.tax_calc import calculate_withholding_tax, income_type_to_a_code

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("seed")

# ── Client definitions ──────────────────────────────────────────────────────

CLIENTS = [
    # (name, biz_number, representative, phone, email)
    ("(주)에이상사", "111-22-33333", "박대표", "010-1111-2222", "biz-a@example.com"),
    ("비즈테크", "222-33-44444", "이사장", "010-2222-3333", "ops@biztech.local"),
    ("크라프트커피", "333-44-55555", "김사장", "010-3333-4444", None),
    ("하나물류", "444-55-66666", "정대표", "010-4444-5555", "hana@logistics.kr"),
    ("스타디자인", "555-66-77777", "최실장", "010-5555-6666", "star@design.co.kr"),
    ("그린팜식품", "666-77-88888", "이농장", "010-6666-7777", "green@farm.kr"),
    ("테크원솔루션", "777-88-99999", "강대표", "010-7777-8888", "tech@one.co.kr"),
]

# ── Employee roster per client ──────────────────────────────────────────────
# (name, rrn, code, hired_date, income_type, base_salary, non_taxable, scenario_tag)
# scenario_tag: "normal", "increase", "decrease", "new_hire", "resigned",
#               "business", "daily", "non_taxable"

ROSTER: dict[int, list[tuple]] = {
    0: [  # (주)에이상사 — 7명
        ("김연호", "900101-1234567", "E001", date(2020, 3, 1), "WAGE", 5_000_000, 0, "increase"),
        ("조명신", "880515-2345678", "E002", date(2019, 1, 15), "WAGE", 3_000_000, 0, "normal"),
        ("박민수", "920808-1456789", "E003", date(2021, 6, 1), "WAGE", 3_500_000, 0, "normal"),
        ("이영수", "850101-1234567", "E004", date(2022, 3, 1), "WAGE", 2_500_000, 0, "normal"),
        ("한지우", "950303-2345678", "E005", date(2023, 9, 1), "WAGE", 2_800_000, 200_000, "non_taxable"),
        ("윤서준", "970707-1456789", "E006", date(2024, 1, 1), "WAGE", 2_200_000, 0, "decrease"),
        ("송미래", "000215-4567890", "E007", date(2026, 4, 1), "WAGE", 2_500_000, 0, "new_hire"),
    ],
    1: [  # 비즈테크 — 8명
        ("최지원", "910303-2345678", "B001", date(2020, 5, 1), "WAGE", 4_500_000, 200_000, "non_taxable"),
        ("정한별", "950505-1456789", "B002", date(2021, 1, 1), "WAGE", 3_500_000, 0, "normal"),
        ("강하늘", "870707-2456789", "B003", date(2019, 7, 1), "WAGE", 4_000_000, 0, "normal"),
        ("나미경", "930202-2123456", "B004", date(2022, 11, 1), "WAGE", 3_000_000, 0, "increase"),
        ("오태호", "890909-1234567", "B005", date(2020, 2, 1), "WAGE", 3_200_000, 0, "normal"),
        ("임도현", "960606-1345678", "B006", date(2023, 3, 1), "WAGE", 2_800_000, 0, "resigned"),
        ("배수진", "940404-2234567", "B007", date(2024, 6, 1), "WAGE", 2_500_000, 0, "normal"),
        ("류지안", "010818-3456789", "B008", date(2026, 4, 1), "WAGE", 2_300_000, 0, "new_hire"),
    ],
    2: [  # 크라프트커피 — 5명
        ("서은호", "880303-1234567", "C001", date(2021, 2, 1), "WAGE", 3_000_000, 200_000, "non_taxable"),
        ("장하린", "960909-2345678", "C002", date(2022, 8, 1), "WAGE", 2_500_000, 0, "normal"),
        ("문태양", "990101-1456789", "C003", date(2023, 5, 1), "WAGE", 2_300_000, 0, "decrease"),
        ("안세리", "000512-4567890", "C004", date(2024, 1, 1), "WAGE", 2_200_000, 0, "normal"),
        ("곽동우", "870215-1234567", "C005", date(2019, 9, 1), "WAGE", 2_800_000, 0, "resigned"),
    ],
    3: [  # 하나물류 — 6명
        ("이준혁", "850808-1234567", "H001", date(2018, 1, 1), "WAGE", 4_200_000, 0, "normal"),
        ("김소라", "910101-2345678", "H002", date(2020, 6, 1), "WAGE", 3_800_000, 200_000, "non_taxable"),
        ("박찬호", "880505-1456789", "H003", date(2019, 3, 1), "WAGE", 3_500_000, 0, "increase"),
        ("윤하영", "950707-2456789", "H004", date(2022, 9, 1), "WAGE", 2_800_000, 0, "normal"),
        ("정우성", "870303-1345678", "H005", date(2017, 5, 1), "WAGE", 4_500_000, 0, "normal"),
        ("최은비", "990909-2234567", "H006", date(2026, 3, 15), "WAGE", 2_500_000, 0, "new_hire"),
    ],
    4: [  # 스타디자인 — 5명 (사업소득 혼재)
        ("김태리", "920202-2234567", "S001", date(2020, 1, 1), "WAGE", 3_500_000, 0, "normal"),
        ("이동국", "850808-1345678", "S002", date(2019, 4, 1), "WAGE", 4_000_000, 0, "normal"),
        ("박서연", "970101-2456789", "S003", date(2023, 1, 1), "BUSINESS", 5_000_000, 0, "business"),
        ("한승우", "880404-1234567", "S004", date(2021, 7, 1), "BUSINESS", 3_000_000, 0, "business"),
        ("조윤아", "930707-2345678", "S005", date(2022, 11, 1), "WAGE", 2_800_000, 0, "resigned"),
    ],
    5: [  # 그린팜식품 — 7명 (일용직 혼재)
        ("황민호", "860101-1234567", "G001", date(2019, 1, 1), "WAGE", 3_200_000, 200_000, "non_taxable"),
        ("고은서", "940505-2345678", "G002", date(2021, 6, 1), "WAGE", 2_800_000, 0, "normal"),
        ("신재호", "900303-1456789", "G003", date(2020, 3, 1), "WAGE", 3_000_000, 0, "normal"),
        ("전소민", "980707-2456789", "G004", date(2023, 8, 1), "WAGE", 2_500_000, 0, "normal"),
        ("권태식", "870909-1345678", "G005", date(2024, 1, 1), "DAILY", 1_500_000, 0, "daily"),
        ("이봄", "000101-4234567", "G006", date(2024, 3, 1), "DAILY", 1_200_000, 0, "daily"),
        ("차우진", "850505-1234567", "G007", date(2017, 5, 1), "WAGE", 3_800_000, 0, "increase"),
    ],
    6: [  # 테크원솔루션 — 7명
        ("홍길동", "910808-1234567", "T001", date(2020, 2, 1), "WAGE", 5_500_000, 200_000, "non_taxable"),
        ("유재석", "850101-1345678", "T002", date(2018, 1, 1), "WAGE", 6_000_000, 0, "normal"),
        ("강호동", "880303-1456789", "T003", date(2019, 6, 1), "WAGE", 4_500_000, 0, "normal"),
        ("이효리", "920505-2234567", "T004", date(2021, 3, 1), "WAGE", 4_000_000, 0, "decrease"),
        ("신동엽", "870707-1345678", "T005", date(2020, 9, 1), "BUSINESS", 8_000_000, 0, "business"),
        ("박명수", "860909-1456789", "T006", date(2022, 1, 1), "WAGE", 3_500_000, 0, "resigned"),
        ("하하", "940101-1234567", "T007", date(2026, 4, 1), "WAGE", 3_000_000, 0, "new_hire"),
    ],
}

PERIODS = ["2026-01", "2026-02", "2026-03", "2026-04"]


def _salary_for_period(
    base: int, scenario: str, period: str, non_taxable: int
) -> tuple[int, int, bool] | None:
    """Return (total_amount, non_taxable, has_anomaly) or None if employee shouldn't appear."""
    # new_hire: only appears in 2026-04
    if scenario == "new_hire":
        if period == "2026-04":
            return base, non_taxable, False
        return None

    # resigned: doesn't appear in 2026-04
    if scenario == "resigned":
        if period == "2026-04":
            return None
        return base, non_taxable, False

    # increase: doubles in 2026-04
    if scenario == "increase" and period == "2026-04":
        return base * 2, non_taxable, True

    # decrease: halved in 2026-04
    if scenario == "decrease" and period == "2026-04":
        return base // 2, non_taxable, True

    # normal, business, daily, non_taxable: stable amount
    return base, non_taxable, False


async def reset_all(db) -> None:
    # FK 의존성 역순으로 삭제 — 참조하는 쪽 먼저, 참조받는 쪽 나중에
    # secure_tokens.collection_session_id → collection_sessions 이므로
    # SecureToken을 CollectionSession보다 먼저 삭제해야 함
    for model in [
        PayrollEntry,
        CollectionEvent,
        SecureToken,
        CollectionSession,
        Employee,
        Client,
        MonthlyFiling,
        User,
        TaxOffice,
        BusinessTypeCode,
    ]:
        await db.execute(delete(model))


async def main() -> None:
    async with SessionLocal() as db:
        await reset_all(db)

        # ── 사업소득 업종코드 마스터 (40종) ──
        for code, name, desc, rate in BUSINESS_TYPE_CODES:
            db.add(BusinessTypeCode(code=code, name=name, description=desc, tax_rate_percent=rate))
        await db.flush()

        # ── Tax office + admin ──
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

        # ── Clients ──
        # (주) 접두사가 있으면 법인으로 취급
        clients: list[Client] = []
        for name, bn, rep, phone, email in CLIENTS:
            c = Client(
                tax_office_id=office.id,
                business_name=name,
                business_number=bn,
                representative=rep,
                contact_phone=phone,
                contact_email=email,
                is_corporation=name.startswith("(주)"),
            )
            db.add(c)
            clients.append(c)
        await db.flush()

        # ── Employees ──
        all_employees: dict[str, list[tuple[Employee, str, int, int]]] = {}
        # key: client_id, value: list of (Employee, scenario, base_salary, non_taxable)
        total_emp_count = 0

        # 사업소득자 업종코드 매핑
        _biz_type_map = {
            "박서연": "940926",  # 소프트웨어프리랜서 (디자인 외주)
            "한승우": "940926",  # 소프트웨어프리랜서 (개발 외주)
            "신동엽": "940600",  # 자문·고문
        }

        for client_idx, members in ROSTER.items():
            client = clients[client_idx]
            all_employees[client.id] = []
            for name, rrn, code, hired, income_type_str, base, non_tax, scenario in members:
                resigned_at = date(2026, 3, 31) if scenario == "resigned" else None
                emp_status = EmploymentStatus.RESIGNED if scenario == "resigned" else EmploymentStatus.ACTIVE
                biz_code = _biz_type_map.get(name) if income_type_str == "BUSINESS" else None
                e = Employee(
                    client_id=client.id,
                    name=name,
                    rrn_encrypted=encrypt_rrn(rrn),
                    rrn_last4=rrn.replace("-", "")[-4:],
                    employee_code=code,
                    hired_at=hired,
                    resigned_at=resigned_at,
                    status=emp_status,
                    business_type_code=biz_code,
                )
                db.add(e)
                all_employees[client.id].append((e, scenario, base, non_tax))
                total_emp_count += 1
        await db.flush()

        # ── Monthly filings + payroll ──
        for period in PERIODS:
            is_current = period == "2026-04"
            filing = MonthlyFiling(
                tax_office_id=office.id,
                period=period,
                status=MonthlyFilingStatus.REVIEWING if is_current else MonthlyFilingStatus.APPROVED,
            )
            db.add(filing)
            await db.flush()

            total_entries = 0
            for client in clients:
                session = CollectionSession(
                    monthly_filing_id=filing.id,
                    client_id=client.id,
                    request_token=f"seed-{period}-{client.id[:8]}",
                    status=CollectionSessionStatus.NEEDS_REVIEW if is_current else CollectionSessionStatus.APPROVED,
                )
                db.add(session)
                await db.flush()

                for emp, scenario, base, non_tax in all_employees[client.id]:
                    income_type_str = next(
                        (m[4] for m in ROSTER[clients.index(client)] if m[0] == emp.name),
                        "WAGE",
                    )
                    income_type = IncomeType(income_type_str)

                    result = _salary_for_period(base, scenario, period, non_tax)
                    if result is None:
                        continue  # skip (new_hire before start, resigned after leave)

                    amount, non_taxable, has_anomaly = result
                    taxable = amount - non_taxable
                    biz_code = emp.business_type_code if income_type == IncomeType.BUSINESS else None
                    tax = calculate_withholding_tax(
                        income_type, taxable, dependents=1,
                        business_type_code=biz_code,
                    )
                    a_code = income_type_to_a_code(income_type, is_corporation=client.is_corporation)

                    # prev_amount for current period
                    prev_amount = base if is_current else None
                    if scenario == "new_hire" and is_current:
                        prev_amount = None  # no previous for new hires

                    anomaly_notes = None
                    if has_anomaly and is_current:
                        ratio = round(amount / base, 2) if base > 0 else 0
                        anomaly_notes = {
                            "large_change": {
                                "prev": base,
                                "current": amount,
                                "ratio": ratio,
                            }
                        }

                    # 근로소득: salary/bonus 분리 (MVP에서는 전액 salary)
                    salary_amt = amount if income_type == IncomeType.WAGE else None
                    bonus_amt = 0 if income_type == IncomeType.WAGE else None

                    db.add(PayrollEntry(
                        monthly_filing_id=filing.id,
                        collection_session_id=session.id,
                        client_id=client.id,
                        employee_id=emp.id,
                        raw_name=emp.name,
                        income_type=income_type,
                        a_code=a_code,
                        business_type_code=biz_code,
                        total_amount=amount,
                        salary_amount=salary_amt,
                        bonus_amount=bonus_amt,
                        non_taxable=non_taxable,
                        taxable=taxable,
                        income_tax=tax.income_tax,
                        local_tax=tax.local_tax,
                        payment_date=date(int(period[:4]), int(period[5:]), 25),
                        match_status=MatchStatus.MATCHED,
                        prev_amount=prev_amount,
                        anomaly_notes=anomaly_notes,
                        approved=not is_current,
                        dependents=1,
                    ))
                    total_entries += 1

            filing.total_clients = len(clients)
            filing.total_entries = total_entries

        await db.commit()
        log.info("Seed complete.")
        log.info("  Tax office: %s", office.name)
        log.info("  Login: admin@example.com / admin1234!")
        log.info("  Clients: %d, Employees: %d", len(clients), total_emp_count)
        log.info("  Periods: %s", ", ".join(PERIODS))
        log.info("  Scenarios: normal, increase, decrease, new_hire, resigned, business, daily, non_taxable")


if __name__ == "__main__":
    asyncio.run(main())
