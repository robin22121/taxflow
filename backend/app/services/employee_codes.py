"""직원 사원코드 — 위하고 사원코드와 같게 숫자만 쓰는 것이 기본 (2026-09-27 사용자 결정).

위하고 급여자료입력은 엑셀 사원코드로 사원을 찾는다. 이지원천 코드가 U001 처럼 달라
위하고(1)와 맞지 않아 전송이 멈춘 일이 있어, 비워 두면 거래처의 다음 번호를 붙인다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee


async def next_employee_code(db: AsyncSession, client_id: str) -> str:
    """거래처 직원 중 숫자 사원코드의 최댓값 + 1 (없으면 "1")."""
    codes = (
        await db.execute(select(Employee.employee_code).where(Employee.client_id == client_id))
    ).scalars().all()
    numbers = [int(c.strip()) for c in codes if c and c.strip().isdigit()]
    return str(max(numbers, default=0) + 1)


async def employee_code_taken(
    db: AsyncSession, client_id: str, code: str, exclude_employee_id: str | None = None
) -> bool:
    """같은 거래처에 이 사원코드를 쓰는 다른 직원이 있는가."""
    query = select(Employee.id).where(
        Employee.client_id == client_id, Employee.employee_code == code
    )
    if exclude_employee_id:
        query = query.where(Employee.id != exclude_employee_id)
    return (await db.execute(query.limit(1))).scalar_one_or_none() is not None
