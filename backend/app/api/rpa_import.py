"""위하고 → 이지원천 임포트 API (plan/16 §12) — 수임처 기본사항 + 사원 기본사항.

- 전체 가져오기: 사무소 관리자만. 위하고 수임처가 많으면 수십 분~수 시간 걸리고,
  그동안 위하고 자동화 PC는 급여 전송 등 다른 작업을 하지 않는다.
- 개별 가져오기: 사업자번호 1건. 사무소 사용자 누구나.
- 에이전트는 수임처 1건을 끝낼 때마다 결과를 보낸다 → 진행률, 생존 신호.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.rpa import (
    ACTIVE_STATUSES,
    _agent_running_job,
    _office_id,
    _require_office_admin,
    _utcnow,
    get_current_agent,
)
from app.core.deps import get_current_user, get_db
from app.models import Client, RpaAgent, RpaJob, RpaJobKind, RpaJobStatus, User
from app.models.rpa import WEHAGO_IMPORT_KINDS
from app.schemas.rpa import (
    RpaJobOut,
    WehagoClientImportCreate,
    WehagoImportClientIn,
    WehagoImportClientOut,
)
from app.services.wehago_import import (
    ImportedClient,
    ImportedEmployee,
    WehagoImportError,
    apply_client_import,
    bn_digits,
    find_client_by_bn,
    format_bn,
)

router = APIRouter()

ALL_IMPORT_NAME = "위하고 전체 수임처"


async def _active_imports(db: AsyncSession, office_id: str) -> list[RpaJob]:
    return list(
        (
            await db.execute(
                select(RpaJob).where(
                    RpaJob.tax_office_id == office_id,
                    RpaJob.kind.in_(WEHAGO_IMPORT_KINDS),
                    RpaJob.status.in_(ACTIVE_STATUSES),
                )
            )
        ).scalars().all()
    )


@router.post("/imports/master-all", response_model=RpaJobOut, status_code=status.HTTP_201_CREATED)
async def create_master_import(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RpaJob:
    """위하고 전체 수임처 가져오기 — 관리자만. 오래 걸리므로 화면에서 먼저 안내한다."""
    office_id = _require_office_admin(user)
    if any(j.kind == RpaJobKind.WEHAGO_MASTER_IMPORT_ALL for j in await _active_imports(db, office_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "위하고 전체 가져오기가 이미 대기·진행 중입니다.")
    job = RpaJob(
        tax_office_id=office_id,
        kind=RpaJobKind.WEHAGO_MASTER_IMPORT_ALL,
        status=RpaJobStatus.PENDING,
        business_name=ALL_IMPORT_NAME,
        requested_by_user_id=user.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@router.post("/imports/clients", response_model=RpaJobOut, status_code=status.HTTP_201_CREATED)
async def create_client_import(
    payload: WehagoClientImportCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RpaJob:
    """사업자번호 1건 가져오기 — 이지원천에 없으면 새 수임처로, 있으면 빈 칸만 채운다."""
    office_id = _office_id(user)
    digits = bn_digits(payload.business_number)
    if len(digits) != 10:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "사업자번호는 숫자 10자리입니다.")
    for job in await _active_imports(db, office_id):
        if job.kind == RpaJobKind.WEHAGO_MASTER_IMPORT_ALL:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "위하고 전체 가져오기가 대기·진행 중입니다. 끝난 뒤 다시 시도하세요.",
            )
        if bn_digits(job.business_number) == digits:
            raise HTTPException(status.HTTP_409_CONFLICT, "이 사업자번호는 이미 가져오기 대기·진행 중입니다.")

    client = await find_client_by_bn(db, office_id, digits)
    job = RpaJob(
        tax_office_id=office_id,
        kind=RpaJobKind.WEHAGO_CLIENT_IMPORT,
        status=RpaJobStatus.PENDING,
        client_id=client.id if client else None,
        business_number=format_bn(digits),
        business_name=client.business_name if client else f"위하고 수임처 {format_bn(digits)}",
        requested_by_user_id=user.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


@router.get("/imports", response_model=list[RpaJobOut])
async def list_imports(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RpaJob]:
    """최근 가져오기 작업 — 진행률(step_progress)과 수임처별 결과 표시용."""
    office_id = _office_id(user)
    rows = await db.execute(
        select(RpaJob)
        .where(RpaJob.tax_office_id == office_id, RpaJob.kind.in_(WEHAGO_IMPORT_KINDS))
        .order_by(RpaJob.created_at.desc())
        .limit(20)
    )
    return list(rows.scalars().all())


@router.post("/agent/imports/{job_id}/client-result", response_model=WehagoImportClientOut)
async def agent_report_client_import(
    job_id: str,
    payload: WehagoImportClientIn,
    db: AsyncSession = Depends(get_db),
    agent: RpaAgent = Depends(get_current_agent),
) -> WehagoImportClientOut:
    """수임처 1건 반영. 수임처마다 따로 커밋해 중간에 멈춰도 끝낸 수임처는 남는다."""
    job = await _agent_running_job(db, agent, job_id)
    if job.kind not in WEHAGO_IMPORT_KINDS:
        raise HTTPException(status.HTTP_409_CONFLICT, "가져오기 작업이 아닙니다")
    if job.kind == RpaJobKind.WEHAGO_CLIENT_IMPORT and bn_digits(job.business_number) != bn_digits(
        payload.business_number
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"요청한 사업자번호({job.business_number})와 다른 수임처입니다: {payload.business_number}",
        )

    now = _utcnow()
    agent.last_seen_at = now
    # 전체 가져오기는 15분을 넘기므로 수임처 결과를 생존 신호로 쓴다 (claim 의 시간 초과 기준).
    job.claimed_at = now

    entry: dict = {"business_number": format_bn(payload.business_number),
                   "business_name": payload.business_name}
    out = WehagoImportClientOut(
        client_id=None, client_created=False, employees_created=0, employees_updated=0, conflicts=[]
    )
    if payload.error:
        entry |= {"status": "FAILED", "message": payload.error}
    else:
        client = await db.get(Client, job.client_id) if job.client_id else None
        data = ImportedClient(
            business_number=payload.business_number,
            business_name=payload.business_name,
            representative=payload.representative,
            is_corporation=payload.is_corporation,
            business_type=payload.business_type,
            business_item=payload.business_item,
            business_address=payload.business_address,
            contact_phone=payload.contact_phone,
            employees=[ImportedEmployee(**e.model_dump()) for e in payload.employees],
        )
        try:
            result = await apply_client_import(db, job.tax_office_id, data, client=client)
        except WehagoImportError as e:
            entry |= {"status": "FAILED", "message": str(e)}
        else:
            result.client.wehago_synced_at = now
            if job.kind == RpaJobKind.WEHAGO_CLIENT_IMPORT:
                job.client_id = result.client.id
                job.business_name = result.client.business_name
            out = WehagoImportClientOut(
                client_id=result.client.id,
                client_created=result.client_created,
                employees_created=result.employees_created,
                employees_updated=result.employees_updated,
                conflicts=result.conflicts,
            )
            entry |= {
                "status": "SUCCEEDED",
                "client_id": result.client.id,
                "client_created": result.client_created,
                "employees": len(payload.employees),
                "employees_created": result.employees_created,
                "employees_updated": result.employees_updated,
                "conflicts": result.conflicts,
            }

    # JSON 컬럼은 새 객체를 넣어야 변경이 저장된다.
    progress = dict(job.step_progress or {})
    clients = [c for c in progress.get("clients", []) if c.get("business_number") != entry["business_number"]]
    progress["clients"] = [*clients, entry]
    if payload.total:
        progress["total"] = payload.total
    job.step_progress = progress
    await db.commit()
    return out
