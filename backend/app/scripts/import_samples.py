"""samples/ 하위 xlsx 데이터를 DB에 삽입 (2026-01~07만, 8월은 제외).

- 거래처 5개 (사업자번호 123-45-67890 ~ 123-45-67894)
- 사장명·연락처·이메일은 사용자 지정값으로 통일
- 기존 조명신 세무사사무소에 붙는다
- 이미 존재하는 거래처(biz_number 기준)면 override, 없으면 생성
- MonthlyFiling은 tax_office_id+period로 upsert

실행:
    cd backend && uv run python -m app.scripts.import_samples
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy import select

from app.db import SessionLocal
from app.models import (
    Client,
    CollectionSession,
    CollectionSessionStatus,
    Employee,
    EmploymentStatus,
    MonthlyFiling,
    MonthlyFilingStatus,
    PayrollEntry,
    TaxOffice,
)
from app.models.payroll import IncomeType, MatchStatus
from app.services.crypto import encrypt_rrn

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("import_samples")

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES = REPO_ROOT / "samples"

# 통일 값 (사용자 지정)
UNIFIED_PHONE = "010-3640-5642"
UNIFIED_EMAIL = "robin1q84@gmail.com"
UNIFIED_REPRESENTATIVE = "홍길동"

# 삽입할 기간 (8월 제외)
PERIODS = [f"2026-{m:02d}" for m in range(1, 8)]


def parse_hired(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None
    return None


def rrn_last4(raw: str) -> str:
    return re.sub(r"[\s-]", "", raw or "")[-4:]


def read_clients_master() -> list[dict]:
    wb = load_workbook(SAMPLES / "clients.xlsx", data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header, data = rows[0], rows[1:]
    idx = {h: i for i, h in enumerate(header)}
    result = []
    for r in data:
        result.append({
            "biz_number": r[idx["사업자번호"]],
            "name": r[idx["상호"]],
            "industry": r[idx["업종"]],
            "is_corp": r[idx["법인/개인"]] == "법인",
        })
    return result


def read_employees(biz_number: str) -> list[dict]:
    path = SAMPLES / biz_number / "employees.xlsx"
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header, data = rows[0], rows[1:]
    idx = {h: i for i, h in enumerate(header)}
    result = []
    for r in data:
        result.append({
            "code": r[idx["사원코드"]],
            "name": r[idx["사원명"]],
            "rrn": str(r[idx["주민번호"]] or "").strip(),
            "hired": parse_hired(r[idx["입사일"]]),
            "department": r[idx["부서"]],
            "position": r[idx["직급"]],
            "job_type": r[idx["직종"]],
            "income_type": r[idx["소득구분"]] or "WAGE",
            "base_salary": int(r[idx["기본급"]] or 0),
            "meal": int(r[idx["식대(비과세)"]] or 0),
            "car": int(r[idx["자가운전(비과세)"]] or 0),
            "childcare": int(r[idx["육아수당(비과세)"]] or 0),
        })
    return result


def read_payroll(biz_number: str, client_name: str, period: str) -> list[dict]:
    """SmartA/위하고T 22컬럼 급여대장 xlsx → 행 dict 리스트."""
    fname = f"{client_name}-{period.replace('-', '')}.xlsx"
    path = SAMPLES / biz_number / fname
    if not path.exists():
        raise FileNotFoundError(path)
    wb = load_workbook(path, data_only=True)
    ws = wb.active
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < 2:
            continue  # 헤더 2행 스킵
        if row[0] == "합계":
            continue
        emp_code = row[0]
        if emp_code is None:
            continue
        rows.append({
            "code": str(emp_code),
            "name": (row[1] or "").strip() if isinstance(row[1], str) else (row[1] or ""),
            "department": row[2] or "",
            "position": row[3] or "",
            "job_type": row[4] or "",
            "base": int(row[5] or 0),
            "bonus": int(row[6] or 0),
            "meal": int(row[7] or 0),
            "car": int(row[8] or 0),
            "childcare": int(row[9] or 0),
            "total_pay": int(row[10] or 0),
            "np": int(row[11] or 0),
            "hi": int(row[12] or 0),
            "ei": int(row[13] or 0),
            "ltc": int(row[14] or 0),
            "income_tax": int(row[15] or 0),
            "local_tax": int(row[16] or 0),
            "student_loan": int(row[17] or 0),
            "settlement_ins": int(row[18] or 0),
            "rent_support": int(row[19] or 0),
            "total_ded": int(row[20] or 0),
            "net": int(row[21] or 0),
        })
    return rows


async def main() -> None:
    async with SessionLocal() as db:
        # 세무사사무소 (기존 조명신 사용)
        office = (await db.execute(select(TaxOffice))).scalars().first()
        if office is None:
            raise RuntimeError("TaxOffice가 DB에 없습니다. 먼저 seed.py를 실행하세요.")
        log.info("세무사사무소: %s", office.name)

        clients_master = read_clients_master()

        # ── 1. Clients upsert ──
        client_by_biz: dict[str, Client] = {}
        for cm in clients_master:
            existing = (
                await db.execute(
                    select(Client).where(Client.business_number == cm["biz_number"])
                )
            ).scalars().first()
            if existing:
                existing.business_name = cm["name"]
                existing.representative = UNIFIED_REPRESENTATIVE
                existing.contact_phone = UNIFIED_PHONE
                existing.contact_email = UNIFIED_EMAIL
                existing.is_corporation = cm["is_corp"]
                client_by_biz[cm["biz_number"]] = existing
                log.info("  거래처 갱신: %s (%s)", cm["name"], cm["biz_number"])
            else:
                c = Client(
                    tax_office_id=office.id,
                    business_name=cm["name"],
                    business_number=cm["biz_number"],
                    representative=UNIFIED_REPRESENTATIVE,
                    contact_phone=UNIFIED_PHONE,
                    contact_email=UNIFIED_EMAIL,
                    is_corporation=cm["is_corp"],
                )
                db.add(c)
                client_by_biz[cm["biz_number"]] = c
                log.info("  거래처 신규: %s (%s)", cm["name"], cm["biz_number"])
        await db.flush()

        # ── 2. Employees upsert (client × employee_code 기준) ──
        # client_biz -> {employee_code: Employee}
        emp_lookup: dict[str, dict[str, Employee]] = {}
        for cm in clients_master:
            biz = cm["biz_number"]
            client = client_by_biz[biz]
            emp_lookup[biz] = {}
            for e in read_employees(biz):
                existing = (
                    await db.execute(
                        select(Employee).where(
                            Employee.client_id == client.id,
                            Employee.employee_code == e["code"],
                        )
                    )
                ).scalars().first()
                income_type = e["income_type"]
                if existing:
                    existing.name = e["name"]
                    existing.department = e["department"]
                    existing.position = e["position"]
                    existing.job_type = e["job_type"]
                    existing.hired_at = e["hired"]
                    emp_lookup[biz][e["code"]] = existing
                else:
                    # 주민번호 암호화 — 형식오류(장아름 등)여도 문자열로 저장
                    try:
                        rrn_enc = encrypt_rrn(e["rrn"]) if e["rrn"] else None
                    except Exception:
                        rrn_enc = None
                    emp = Employee(
                        client_id=client.id,
                        name=e["name"],
                        rrn_encrypted=rrn_enc,
                        rrn_last4=rrn_last4(e["rrn"]) if e["rrn"] else None,
                        employee_code=e["code"],
                        department=e["department"],
                        position=e["position"],
                        job_type=e["job_type"],
                        hired_at=e["hired"],
                        status=EmploymentStatus.ACTIVE,
                    )
                    db.add(emp)
                    emp_lookup[biz][e["code"]] = emp
            log.info("  [%s] 직원 %d명", cm["name"], len(emp_lookup[biz]))
        await db.flush()

        # ── 3. Monthly filing + collection session + payroll entries ──
        for period in PERIODS:
            filing = (
                await db.execute(
                    select(MonthlyFiling).where(
                        MonthlyFiling.tax_office_id == office.id,
                        MonthlyFiling.period == period,
                    )
                )
            ).scalars().first()
            if filing is None:
                filing = MonthlyFiling(
                    tax_office_id=office.id,
                    period=period,
                    status=MonthlyFilingStatus.APPROVED,
                )
                db.add(filing)
                await db.flush()
                log.info("  월별 신고 신규: %s", period)
            else:
                log.info("  월별 신고 재사용: %s (%s)", period, filing.status.value)

            for cm in clients_master:
                client = client_by_biz[cm["biz_number"]]
                emp_map = emp_lookup[cm["biz_number"]]

                # 이 (client, filing) 조합의 기존 CollectionSession 재사용
                session = (
                    await db.execute(
                        select(CollectionSession).where(
                            CollectionSession.monthly_filing_id == filing.id,
                            CollectionSession.client_id == client.id,
                        )
                    )
                ).scalars().first()
                if session is None:
                    session = CollectionSession(
                        monthly_filing_id=filing.id,
                        client_id=client.id,
                        request_token=f"sample-{period}-{cm['biz_number']}",
                        status=CollectionSessionStatus.APPROVED,
                    )
                    db.add(session)
                    await db.flush()
                else:
                    # 이 세션에 붙은 기존 PayrollEntry 삭제 (재삽입)
                    entries = (
                        await db.execute(
                            select(PayrollEntry).where(
                                PayrollEntry.collection_session_id == session.id,
                            )
                        )
                    ).scalars().all()
                    for e in entries:
                        await db.delete(e)
                    await db.flush()

                rows = read_payroll(cm["biz_number"], cm["name"], period)
                pay_day = date(int(period[:4]), int(period[5:]), 25)
                for r in rows:
                    emp = emp_map.get(r["code"])
                    match_status = MatchStatus.MATCHED if emp else MatchStatus.NEW_HIRE_SUSPECTED
                    non_taxable = r["meal"] + r["car"] + r["childcare"]
                    taxable = r["total_pay"] - non_taxable
                    a_code = "A01" if client.is_corporation else "A02"
                    db.add(PayrollEntry(
                        monthly_filing_id=filing.id,
                        collection_session_id=session.id,
                        client_id=client.id,
                        employee_id=emp.id if emp else None,
                        raw_name=r["name"] or r["code"],
                        income_type=IncomeType.WAGE,
                        a_code=a_code,
                        total_amount=r["total_pay"],
                        salary_amount=r["base"],
                        bonus_amount=r["bonus"],
                        non_taxable=non_taxable,
                        meal_amount=r["meal"],
                        car_amount=r["car"],
                        childcare_amount=r["childcare"],
                        taxable=taxable,
                        national_pension=r["np"],
                        health_insurance=r["hi"],
                        employment_insurance=r["ei"],
                        longterm_care=r["ltc"],
                        income_tax=r["income_tax"],
                        local_tax=r["local_tax"],
                        student_loan=r["student_loan"],
                        settlement_insurance=r["settlement_ins"],
                        rent_support=r["rent_support"],
                        payment_date=pay_day,
                        match_status=match_status,
                        approved=True,
                        dependents=1,
                    ))

            await db.flush()

        await db.commit()
        log.info("\n샘플 데이터 삽입 완료 (2026-01~07)")


if __name__ == "__main__":
    asyncio.run(main())
