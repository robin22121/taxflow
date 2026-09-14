"""위하고 급여 업로드 RPA — 전송 작업 큐와 사무실 PC 에이전트 API (plan/16-wehago-rpa.md).

세무사 화면(사용자 JWT)이 작업을 등록하고, 사무실 PC 에이전트(``X-Agent-Token``)가
작업을 한 건씩 가져가 위하고T에 업로드한 뒤 결과를 회신한다. 에이전트는 서버로
나가는 HTTPS만 쓰므로 사무실 방화벽을 열 필요가 없다.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db
from app.models import (
    Client,
    MonthlyFiling,
    PayrollEntry,
    RpaAgent,
    RpaJob,
    RpaJobKind,
    RpaJobStatus,
    User,
)
from app.schemas.rpa import (
    RpaAgentCreate,
    RpaAgentIssued,
    RpaAgentOut,
    RpaClaimOut,
    RpaJobOut,
    RpaJobResultIn,
    WehagoUploadCreate,
)
from app.services.payroll_excel import generate_payroll_excel

router = APIRouter()

AGENT_TOKEN_PREFIX = "rpa_"
# 에이전트가 이 시간 안에 결과를 회신하지 않으면 멈춘 것으로 본다.
RUNNING_TIMEOUT = timedelta(minutes=15)
ACTIVE_STATUSES = (RpaJobStatus.PENDING, RpaJobStatus.RUNNING)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_utc(dt: datetime) -> datetime:
    """SQLite는 tz 정보를 떼고 돌려주므로 UTC로 간주한다."""
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _office_id(user: User) -> str:
    if not user.tax_office_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "세무사사무소 계정만 사용할 수 있습니다")
    return user.tax_office_id


def _require_office_admin(user: User) -> str:
    office_id = _office_id(user)
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "사무소 관리자만 할 수 있습니다")
    return office_id


def _finish(job: RpaJob, job_status: RpaJobStatus, message: str | None, now: datetime) -> None:
    job.status = job_status
    job.result_message = message
    job.finished_at = now


async def get_current_agent(
    x_agent_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> RpaAgent:
    if not x_agent_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "에이전트 토큰이 필요합니다")
    agent = (
        await db.execute(select(RpaAgent).where(RpaAgent.token_hash == _hash_token(x_agent_token)))
    ).scalar_one_or_none()
    if not agent or agent.revoked_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "유효하지 않은 에이전트 토큰입니다")
    return agent


# ---------------------------------------------------------------------------
# 에이전트 발급·폐기 (세무사 화면)
# ---------------------------------------------------------------------------


@router.post("/agents", response_model=RpaAgentIssued, status_code=status.HTTP_201_CREATED)
async def issue_agent(
    payload: RpaAgentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RpaAgentIssued:
    office_id = _require_office_admin(user)
    token = AGENT_TOKEN_PREFIX + secrets.token_urlsafe(32)
    agent = RpaAgent(tax_office_id=office_id, name=payload.name, token_hash=_hash_token(token))
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return RpaAgentIssued(**RpaAgentOut.model_validate(agent).model_dump(), token=token)


@router.get("/agents", response_model=list[RpaAgentOut])
async def list_agents(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RpaAgent]:
    office_id = _office_id(user)
    rows = await db.execute(
        select(RpaAgent)
        .where(RpaAgent.tax_office_id == office_id)
        .order_by(RpaAgent.created_at.desc())
    )
    return list(rows.scalars().all())


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    office_id = _require_office_admin(user)
    agent = await db.get(RpaAgent, agent_id)
    if not agent or agent.tax_office_id != office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "에이전트를 찾을 수 없습니다")
    if agent.revoked_at is None:
        agent.revoked_at = _utcnow()
        await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# 전송 작업 등록·조회·취소 (세무사 화면)
# ---------------------------------------------------------------------------


@router.post(
    "/wehago-uploads", response_model=list[RpaJobOut], status_code=status.HTTP_201_CREATED
)
async def create_wehago_uploads(
    payload: WehagoUploadCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RpaJob]:
    """승인 완료된 거래처의 급여대장을 위하고 전송 대기열에 올린다."""
    office_id = _office_id(user)
    filing = await db.get(MonthlyFiling, payload.filing_id)
    if not filing or filing.tax_office_id != office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    client_ids = list(dict.fromkeys(payload.client_ids))
    clients = (
        await db.execute(
            select(Client).where(Client.id.in_(client_ids), Client.tax_office_id == office_id)
        )
    ).scalars().all()
    by_id = {c.id: c for c in clients}
    if len(by_id) != len(client_ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "거래처를 찾을 수 없습니다")
    ordered = [by_id[cid] for cid in client_ids]

    def names(ids: set[str]) -> str:
        return ", ".join(c.business_name for c in ordered if c.id in ids)

    # 위하고 수임처는 사업자번호로 찾는다 — 없으면 엉뚱한 회사에 올릴 위험이 있다.
    no_number = {c.id for c in ordered if not (c.business_number or "").strip()}
    if no_number:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"사업자번호가 없는 거래처는 위하고로 전송할 수 없습니다: {names(no_number)}.",
        )

    rows = (
        await db.execute(
            select(PayrollEntry.client_id, PayrollEntry.approved).where(
                PayrollEntry.monthly_filing_id == filing.id,
                PayrollEntry.client_id.in_(client_ids),
            )
        )
    ).all()
    unapproved = {cid for cid, approved in rows if not approved}
    if unapproved:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"미승인 자료가 있는 거래처는 전송할 수 없습니다: {names(unapproved)}. "
            "먼저 검증·승인을 완료하세요.",
        )
    empty = set(client_ids) - {cid for cid, _ in rows}
    if empty:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"자료가 없는 거래처는 전송할 수 없습니다: {names(empty)}."
        )

    active = set(
        (
            await db.execute(
                select(RpaJob.client_id).where(
                    RpaJob.monthly_filing_id == filing.id,
                    RpaJob.client_id.in_(client_ids),
                    RpaJob.kind == RpaJobKind.WEHAGO_PAYROLL_UPLOAD,
                    RpaJob.status.in_(ACTIVE_STATUSES),
                )
            )
        ).scalars().all()
    )
    if active:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"이미 위하고 전송이 대기·진행 중인 거래처입니다: {names(active)}.",
        )

    jobs = [
        RpaJob(
            tax_office_id=office_id,
            kind=RpaJobKind.WEHAGO_PAYROLL_UPLOAD,
            status=RpaJobStatus.PENDING,
            monthly_filing_id=filing.id,
            client_id=c.id,
            period=filing.period,
            business_number=c.business_number.strip(),
            business_name=c.business_name,
            requested_by_user_id=user.id,
        )
        for c in ordered
    ]
    db.add_all(jobs)
    await db.commit()
    for job in jobs:
        await db.refresh(job)
    return jobs


@router.get("/jobs", response_model=list[RpaJobOut])
async def list_jobs(
    filing_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RpaJob]:
    office_id = _office_id(user)
    query = select(RpaJob).where(RpaJob.tax_office_id == office_id)
    if filing_id:
        query = query.where(RpaJob.monthly_filing_id == filing_id)
    rows = await db.execute(query.order_by(RpaJob.created_at.desc()).limit(200))
    return list(rows.scalars().all())


@router.post("/jobs/{job_id}/cancel", response_model=RpaJobOut)
async def cancel_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RpaJob:
    office_id = _office_id(user)
    job = await db.get(RpaJob, job_id)
    if not job or job.tax_office_id != office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작업을 찾을 수 없습니다")
    # 에이전트가 이미 위하고에서 작업 중이면 중간에 멈출 수 없다.
    result = await db.execute(
        update(RpaJob)
        .where(RpaJob.id == job_id, RpaJob.status == RpaJobStatus.PENDING)
        .values(status=RpaJobStatus.CANCELED, finished_at=_utcnow())
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "대기 중인 작업만 취소할 수 있습니다")
    await db.commit()
    await db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# 에이전트 전용 (X-Agent-Token)
# ---------------------------------------------------------------------------


@router.post("/agent/claim", response_model=RpaClaimOut)
async def claim_job(
    db: AsyncSession = Depends(get_db),
    agent: RpaAgent = Depends(get_current_agent),
) -> RpaClaimOut:
    """대기 중인 작업을 한 건 가져간다. 에이전트는 손이 비었을 때만 호출한다."""
    now = _utcnow()
    agent.last_seen_at = now

    running = (
        await db.execute(
            select(RpaJob).where(
                RpaJob.tax_office_id == agent.tax_office_id,
                RpaJob.status == RpaJobStatus.RUNNING,
            )
        )
    ).scalars().all()
    busy = False
    for job in running:
        if job.agent_id == agent.id:
            # 자기 작업이 남아 있는데 새로 요청했다면 도중에 재시작된 것이다.
            _finish(
                job,
                RpaJobStatus.FAILED,
                "에이전트가 작업 도중 재시작되어 중단됨 — 위하고에 실제 반영됐는지 확인하세요",
                now,
            )
        elif job.claimed_at and now - _as_utc(job.claimed_at) > RUNNING_TIMEOUT:
            _finish(
                job,
                RpaJobStatus.FAILED,
                "에이전트 응답 시간 초과 — 위하고에 실제 반영됐는지 확인하세요",
                now,
            )
        else:
            busy = True
    if busy:
        # 위하고 계정 하나를 동시에 쓰면 세션이 끊기므로 사무소당 한 건씩만 돌린다.
        await db.commit()
        return RpaClaimOut(job=None)

    next_id = (
        await db.execute(
            select(RpaJob.id)
            .where(
                RpaJob.tax_office_id == agent.tax_office_id,
                RpaJob.status == RpaJobStatus.PENDING,
            )
            .order_by(RpaJob.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()
    if next_id is None:
        await db.commit()
        return RpaClaimOut(job=None)

    result = await db.execute(
        update(RpaJob)
        .where(RpaJob.id == next_id, RpaJob.status == RpaJobStatus.PENDING)
        .values(status=RpaJobStatus.RUNNING, agent_id=agent.id, claimed_at=now)
    )
    await db.commit()
    if result.rowcount == 0:  # 다른 에이전트가 먼저 가져감
        return RpaClaimOut(job=None)
    job = await db.get(RpaJob, next_id)
    await db.refresh(job)
    return RpaClaimOut(job=RpaJobOut.model_validate(job))


async def _agent_running_job(db: AsyncSession, agent: RpaAgent, job_id: str) -> RpaJob:
    job = await db.get(RpaJob, job_id)
    if not job or job.tax_office_id != agent.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작업을 찾을 수 없습니다")
    if job.status != RpaJobStatus.RUNNING or job.agent_id != agent.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "이 에이전트가 진행 중인 작업이 아닙니다")
    return job


@router.get("/agent/jobs/{job_id}/payroll-excel")
async def agent_download_payroll_excel(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    agent: RpaAgent = Depends(get_current_agent),
) -> Response:
    job = await _agent_running_job(db, agent, job_id)
    entries = list(
        (
            await db.execute(
                select(PayrollEntry)
                .where(
                    PayrollEntry.monthly_filing_id == job.monthly_filing_id,
                    PayrollEntry.client_id == job.client_id,
                )
                .options(selectinload(PayrollEntry.employee))
            )
        )
        .scalars()
        .all()
    )
    # 등록 뒤에 승인이 풀렸거나 자료가 지워졌을 수 있으므로 내려주기 직전에 다시 막는다.
    if not entries:
        raise HTTPException(status.HTTP_409_CONFLICT, "자료가 없습니다.")
    if any(not e.approved for e in entries):
        raise HTTPException(status.HTTP_409_CONFLICT, "미승인 자료가 있어 업로드할 수 없습니다.")

    blob = generate_payroll_excel(entries, period=job.period, client_name=job.business_name)
    agent.last_seen_at = _utcnow()
    await db.commit()
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="payroll_{job.period}.xlsx"'},
    )


@router.post("/agent/jobs/{job_id}/result", response_model=RpaJobOut)
async def agent_report_result(
    job_id: str,
    payload: RpaJobResultIn,
    db: AsyncSession = Depends(get_db),
    agent: RpaAgent = Depends(get_current_agent),
) -> RpaJob:
    job = await _agent_running_job(db, agent, job_id)
    now = _utcnow()
    agent.last_seen_at = now
    _finish(job, RpaJobStatus(payload.status), payload.message, now)
    await db.commit()
    await db.refresh(job)
    return job
