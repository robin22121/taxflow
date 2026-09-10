"""세무사 승인 창구 — 사업주 포털이 통보한 입·퇴사 (plan/12-owner-portal.md §5.2).

승인 전까지 ``Employee`` 마스터는 건드리지 않는다. 이 게이트가 있어야
급여대장 엑셀과 4대보험 신고서가 신뢰할 수 있는 데이터로 생성된다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db
from app.models import (
    ChangeRequestStatus,
    ChangeType,
    Client,
    Employee,
    EmployeeChangeRequest,
    EmploymentStatus,
    User,
)

router = APIRouter()


class ChangeRequestOut(BaseModel):
    id: str
    client_id: str
    client_name: str
    change_type: str
    name: str
    hired_at: date | None
    resigned_at: date | None
    note: str | None
    status: str


def _out(request: EmployeeChangeRequest) -> ChangeRequestOut:
    return ChangeRequestOut(
        id=request.id,
        client_id=request.client_id,
        client_name=request.client.business_name,
        change_type=request.change_type.value,
        name=request.name,
        hired_at=request.hired_at,
        resigned_at=request.resigned_at,
        note=request.note,
        status=request.status.value,
    )


async def _request_or_404(
    db: AsyncSession, request_id: str, user: User
) -> EmployeeChangeRequest:
    request = (
        await db.execute(
            select(EmployeeChangeRequest)
            .where(EmployeeChangeRequest.id == request_id)
            .options(selectinload(EmployeeChangeRequest.client))
        )
    ).scalar_one_or_none()
    if not request or request.client.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "요청을 찾을 수 없습니다")
    return request


@router.get("", response_model=list[ChangeRequestOut])
async def list_change_requests(
    status_filter: str = Query("PENDING", alias="status"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ChangeRequestOut]:
    """대기 중인 입·퇴사 통보 목록. ``status=ALL``이면 처리된 건까지 본다."""
    stmt = (
        select(EmployeeChangeRequest)
        .join(Client, Client.id == EmployeeChangeRequest.client_id)
        .where(Client.tax_office_id == user.tax_office_id)
        .options(selectinload(EmployeeChangeRequest.client))
        .order_by(EmployeeChangeRequest.created_at.desc())
    )
    if status_filter != "ALL":
        try:
            wanted = ChangeRequestStatus(status_filter)
        except ValueError as e:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "알 수 없는 상태입니다") from e
        stmt = stmt.where(EmployeeChangeRequest.status == wanted)

    rows = (await db.execute(stmt)).scalars().all()
    return [_out(row) for row in rows]


@router.post("/{request_id}/approve", response_model=ChangeRequestOut)
async def approve_change_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChangeRequestOut:
    """승인 — 이때 비로소 ``Employee`` 마스터가 바뀐다."""
    request = await _request_or_404(db, request_id, user)
    if request.status is not ChangeRequestStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 처리된 요청입니다")

    if request.change_type is ChangeType.HIRE:
        employee = Employee(
            client_id=request.client_id,
            name=request.name,
            hired_at=request.hired_at,
            status=EmploymentStatus.ACTIVE,
        )
        db.add(employee)
        await db.flush()
        request.employee_id = employee.id
    else:
        employee = await db.get(Employee, request.employee_id) if request.employee_id else None
        if employee is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "대상 직원이 이미 삭제되었습니다")
        employee.resigned_at = request.resigned_at
        employee.status = EmploymentStatus.RESIGNED

    request.status = ChangeRequestStatus.APPROVED
    request.reviewed_at = datetime.now(UTC)
    request.reviewed_by = user.id
    await db.commit()
    await db.refresh(request)
    return _out(request)


@router.post("/{request_id}/reject", response_model=ChangeRequestOut)
async def reject_change_request(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChangeRequestOut:
    request = await _request_or_404(db, request_id, user)
    if request.status is not ChangeRequestStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 처리된 요청입니다")
    request.status = ChangeRequestStatus.REJECTED
    request.reviewed_at = datetime.now(UTC)
    request.reviewed_by = user.id
    await db.commit()
    await db.refresh(request)
    return _out(request)
