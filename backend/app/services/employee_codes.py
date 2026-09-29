"""직원 사원코드 — 위하고 사원코드와 같게 숫자만 쓰는 것이 기본 (2026-09-27 사용자 결정).

위하고 급여자료입력은 엑셀 사원코드로 사원을 찾는다. 이지원천 코드가 U001 처럼 달라
위하고(1)와 맞지 않아 전송이 멈춘 일이 있어, 비워 두면 거래처의 다음 번호를 붙인다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Employee
from app.models.income_type import IncomeType


async def next_employee_code(db: AsyncSession, client_id: str, income_type: IncomeType) -> str:
    """거래처의 같은 소득구분 안에서 숫자 사원코드의 최댓값 + 1 (없으면 "1").

    소득구분(근로/사업/기타/일용)마다 번호가 독립적이라 근로1·사업1·기타1처럼
    같은 번호를 소득구분별로 각각 쓸 수 있다.
    """
    codes = (
        await db.execute(
            select(Employee.employee_code).where(
                Employee.client_id == client_id, Employee.income_type == income_type
            )
        )
    ).scalars().all()
    numbers = [int(c.strip()) for c in codes if c and c.strip().isdigit()]
    return str(max(numbers, default=0) + 1)


async def employee_code_taken(
    db: AsyncSession,
    client_id: str,
    income_type: IncomeType,
    code: str,
    exclude_employee_id: str | None = None,
) -> bool:
    """같은 거래처·같은 소득구분에 이 사원코드를 쓰는 다른 직원이 있는가."""
    query = select(Employee.id).where(
        Employee.client_id == client_id,
        Employee.income_type == income_type,
        Employee.employee_code == code,
    )
    if exclude_employee_id:
        query = query.where(Employee.id != exclude_employee_id)
    return (await db.execute(query.limit(1))).scalar_one_or_none() is not None
