"""위하고 → 이지원천 임포트 — 수임처 1건의 기본사항·사원 기본사항을 반영한다 (plan/16 §12).

에이전트가 위하고 화면·사원자료 엑셀에서 필요한 항목만 뽑아 보낸다
(계좌·연락처·보험료 등은 노트북 밖으로 나오지 않는다).

반영 원칙 (§12-5)
- 새 수임처·사원은 만든다.
- 이미 있으면 **빈 칸만 채운다.** 값이 다르면 덮지 않고 차이(conflicts)로 돌려준다.
- 예외: 사원코드는 위하고 사원 연결 키라 위하고 값으로 맞춘다 (급여 업로드가 이 코드로 사원을 찾는다).
- 사원 매칭 순서: 사원코드 → 주민번호 → 사원코드 없는 동명이인 없는 이름.
- 주민번호는 암호화 저장하고, 차이 보고에도 값은 남기지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, Employee
from app.models.employee import EmploymentStatus
from app.services.crypto import decrypt_rrn, encrypt_rrn, normalize_rrn, rrn_last4


class WehagoImportError(ValueError):
    """이 수임처는 반영하지 않는다 (요청 수임처와 다름 등)."""


@dataclass
class ImportedEmployee:
    employee_code: str
    name: str
    rrn: str | None = None
    hired_at: date | None = None
    resigned_at: date | None = None
    department: str | None = None
    position: str | None = None
    job_type: str | None = None


@dataclass
class ImportedClient:
    business_number: str
    business_name: str
    representative: str | None = None
    is_corporation: bool | None = None
    business_type: str | None = None
    business_item: str | None = None
    business_address: str | None = None
    contact_phone: str | None = None
    employees: list[ImportedEmployee] = field(default_factory=list)


@dataclass
class ImportOutcome:
    client: Client
    client_created: bool
    employees_created: int = 0
    employees_updated: int = 0
    # {"target": "수임처"|사원명, "field": 항목, "current": 이지원천 값, "wehago": 위하고 값}
    conflicts: list[dict[str, Any]] = field(default_factory=list)


def _safe_rrn(raw: str | None) -> str:
    """13자리 주민번호, 형식이 틀리면 "" (매칭·저장에 쓰지 않는다)."""
    try:
        return normalize_rrn(raw) if raw else ""
    except ValueError:
        return ""


def bn_digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def format_bn(value: str) -> str:
    d = bn_digits(value)
    return f"{d[:3]}-{d[3:5]}-{d[5:]}" if len(d) == 10 else value.strip()


def _fill(obj: Any, attr: str, value: Any, target: str, label: str, out: ImportOutcome) -> bool:
    """빈 칸이면 채우고 True, 값이 다르면 차이로 남긴다."""
    if value in (None, ""):
        return False
    current = getattr(obj, attr)
    if current in (None, ""):
        setattr(obj, attr, value)
        return True
    if current != value:
        out.conflicts.append(
            {"target": target, "field": label, "current": str(current), "wehago": str(value)}
        )
    return False


async def find_client_by_bn(db: AsyncSession, office_id: str, business_number: str) -> Client | None:
    digits = bn_digits(business_number)
    rows = (
        await db.execute(
            select(Client).where(Client.tax_office_id == office_id, Client.business_number.is_not(None))
        )
    ).scalars().all()
    matches = [c for c in rows if bn_digits(c.business_number) == digits]
    return matches[0] if matches else None


async def apply_client_import(
    db: AsyncSession,
    office_id: str,
    data: ImportedClient,
    *,
    client: Client | None = None,
    today: date | None = None,
) -> ImportOutcome:
    """수임처 1건을 반영한다. ``client``를 주면 그 수임처에 반영한다 (사업자번호 일치 검사)."""
    today = today or date.today()
    digits = bn_digits(data.business_number)
    if len(digits) != 10:
        raise WehagoImportError(f"사업자번호 형식이 올바르지 않습니다: {data.business_number!r}")

    if client is not None and client.business_number and bn_digits(client.business_number) != digits:
        raise WehagoImportError(
            f"요청 수임처({client.business_number})와 위하고 수임처({data.business_number})의 "
            "사업자번호가 다릅니다"
        )
    if client is None:
        client = await find_client_by_bn(db, office_id, digits)

    created = client is None
    if created:
        client = Client(
            tax_office_id=office_id,
            business_name=data.business_name.strip(),
            business_number=format_bn(digits),
            is_corporation=bool(data.is_corporation),
        )
        db.add(client)
        await db.flush()
    out = ImportOutcome(client=client, client_created=created)

    target = "수임처"
    _fill(client, "business_number", format_bn(digits), target, "사업자번호", out)
    _fill(client, "representative", data.representative, target, "대표자", out)
    _fill(client, "business_type", data.business_type, target, "업태", out)
    _fill(client, "business_item", data.business_item, target, "종목", out)
    _fill(client, "business_address", data.business_address, target, "사업장 주소", out)
    _fill(client, "contact_phone", data.contact_phone, target, "전화번호", out)
    if not created and data.business_name.strip() != client.business_name:
        out.conflicts.append({"target": target, "field": "상호",
                              "current": client.business_name, "wehago": data.business_name})
    if data.is_corporation is not None and not created and client.is_corporation != data.is_corporation:
        out.conflicts.append({"target": target, "field": "법인/개인",
                              "current": "법인" if client.is_corporation else "개인",
                              "wehago": "법인" if data.is_corporation else "개인"})

    await _apply_employees(db, client, data.employees, out, today)
    return out


async def _apply_employees(
    db: AsyncSession,
    client: Client,
    incoming: list[ImportedEmployee],
    out: ImportOutcome,
    today: date,
) -> None:
    existing = list(
        (await db.execute(select(Employee).where(Employee.client_id == client.id))).scalars().all()
    )
    by_code = {e.employee_code: e for e in existing if e.employee_code}
    by_rrn: dict[str, Employee] = {}
    for e in existing:
        if e.rrn_encrypted and (known := _safe_rrn(decrypt_rrn(e.rrn_encrypted))):
            by_rrn[known] = e
    uncoded_by_name: dict[str, list[Employee]] = {}
    for e in existing:
        if not e.employee_code:
            uncoded_by_name.setdefault(e.name, []).append(e)
    claimed: set[str] = set()

    for row in incoming:
        code = row.employee_code.strip()
        rrn = _safe_rrn(row.rrn)
        emp = by_code.get(code)
        if emp is None and rrn:
            emp = by_rrn.get(rrn)
        if emp is None:
            same_name = [e for e in uncoded_by_name.get(row.name, []) if e.id not in claimed]
            if len(same_name) == 1:
                emp = same_name[0]
        if emp is not None and emp.id in claimed:
            emp = None  # 한 이지원천 사원에 위하고 사원 둘을 붙이지 않는다

        resigned = row.resigned_at is not None and row.resigned_at <= today
        if emp is None:
            emp = Employee(
                client_id=client.id,
                name=row.name,
                employee_code=code,
                rrn_encrypted=encrypt_rrn(rrn) if rrn else None,
                rrn_last4=rrn_last4(rrn) if rrn else None,
                hired_at=row.hired_at,
                resigned_at=row.resigned_at,
                department=row.department,
                position=row.position,
                job_type=row.job_type,
                status=EmploymentStatus.RESIGNED if resigned else EmploymentStatus.ACTIVE,
            )
            db.add(emp)
            await db.flush()
            claimed.add(emp.id)
            out.employees_created += 1
            continue

        claimed.add(emp.id)
        changed = False
        if emp.employee_code != code:
            # 위하고 사원 연결 키 — 위하고 값으로 맞추고 무엇이 바뀌었는지 남긴다
            if emp.employee_code:
                out.conflicts.append({"target": row.name, "field": "사원코드(위하고 값으로 변경)",
                                      "current": emp.employee_code, "wehago": code})
            emp.employee_code = code
            changed = True
        if rrn:
            if not emp.rrn_encrypted:
                emp.rrn_encrypted = encrypt_rrn(rrn)
                emp.rrn_last4 = rrn_last4(rrn)
                changed = True
            elif _safe_rrn(decrypt_rrn(emp.rrn_encrypted)) != rrn:
                out.conflicts.append({"target": row.name, "field": "주민번호",
                                      "current": "(다름)", "wehago": "(다름)"})
        changed |= _fill(emp, "name", row.name, row.name, "사원명", out)
        changed |= _fill(emp, "hired_at", row.hired_at, row.name, "입사일", out)
        if _fill(emp, "resigned_at", row.resigned_at, row.name, "퇴사일", out):
            changed = True
            if resigned:
                emp.status = EmploymentStatus.RESIGNED
        changed |= _fill(emp, "department", row.department, row.name, "부서", out)
        changed |= _fill(emp, "position", row.position, row.name, "직급", out)
        changed |= _fill(emp, "job_type", row.job_type, row.name, "직종", out)
        if changed:
            out.employees_updated += 1
