"""위하고 급여 업로드 RPA — 전송 작업 큐와 사무실 PC 에이전트 API (plan/16-wehago-rpa.md).

세무사 화면(사용자 JWT)이 작업을 등록하고, 사무실 PC 에이전트(``X-Agent-Token``)가
작업을 한 건씩 가져가 위하고T에 업로드한 뒤 결과를 회신한다. 에이전트는 서버로
나가는 HTTPS만 쓰므로 사무실 방화벽을 열 필요가 없다.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import ColumnElement, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db
from app.models import (
    Client,
    ClientFilingResult,
    ClientPayrollDefault,
    Employee,
    FilingResultSource,
    MonthlyFiling,
    PayrollEntry,
    RpaAgent,
    RpaJob,
    RpaJobKind,
    RpaJobStatus,
    RpaNotification,
    RpaNotificationKind,
    User,
)
from app.models.payroll import IncomeType
from app.models.rpa import WEHAGO_IMPORT_KINDS, WEHAGO_INPUT_KINDS, WEHAGO_JOB_KINDS
from app.schemas.rpa import (
    AgentFilingResultIn,
    FilingResultOut,
    ProductionCreate,
    PublishFilingResultOut,
    RpaAgentCreate,
    RpaAgentIssued,
    RpaActivityJobOut,
    RpaAgentOut,
    RpaClaimOut,
    RpaJobOut,
    RpaJobResultIn,
    RpaNotificationOut,
    IncomeTypeStatus,
    WehagoUploadCreate,
    WehagoUploadPreviewRow,
)
from app.services.payroll_defaults import resolve_pay_date
from app.services.payroll_excel import PayrollExcelError, generate_payroll_excel
from app.services.smarta_business_xls import generate_smarta_business_xls
from app.services.smarta_other_income_xls import RESIDENT_INCOME_CODE_LABELS, generate_smarta_other_income_xls

router = APIRouter()

# 게이트 1 자동입력이 있는 소득유형 — plan/16 §4-1·§13-3-4 (2026-09-30 사업소득,
# 2026-10-01 기타소득 추가 — 엑셀 생성기 openpyxl 전환 + 완료 잠금 해제까지 실전
# 업로드 검증 완료, §13-3-3).
# 일용소득은 자료입력 엑셀 업로드가 아직 신뢰할 수 없어(plan/16 §13-3-1) 제외돼 있다.
# 하나가 생기면 여기와 INPUT_JOB_KIND_BY_INCOME_TYPE에 함께 추가한다.
AUTOMATED_INCOME_TYPES = {IncomeType.WAGE, IncomeType.BUSINESS, IncomeType.OTHER}
# 소득유형별로 게이트 1 화면이 달라(근로=SWSA0101, 사업=SWBU0102, 기타=SWET0102) RpaJobKind도 나뉜다.
INPUT_JOB_KIND_BY_INCOME_TYPE = {
    IncomeType.WAGE: RpaJobKind.WEHAGO_PAYROLL_INPUT,
    IncomeType.BUSINESS: RpaJobKind.WEHAGO_BUSINESS_INPUT,
    IncomeType.OTHER: RpaJobKind.WEHAGO_OTHER_INPUT,
}
_INCOME_TYPE_LABEL = {
    IncomeType.WAGE: "근로소득",
    IncomeType.BUSINESS: "사업소득",
    IncomeType.OTHER: "기타소득",
    IncomeType.DAILY: "일용소득",
    IncomeType.RETIREMENT: "퇴직소득",
}

AGENT_TOKEN_PREFIX = "rpa_"
# 에이전트가 이 시간 안에 결과를 회신하지 않으면 멈춘 것으로 본다.
RUNNING_TIMEOUT = timedelta(minutes=15)
ACTIVE_STATUSES = (RpaJobStatus.PENDING, RpaJobStatus.RUNNING)
KST = ZoneInfo("Asia/Seoul")  # 작업바 '오늘' 기준


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


async def _pay_date(
    db: AsyncSession, filing_id: str, client_id: str, period: str
) -> tuple[date | None, str | None]:
    """위하고 급여자료입력 지급일 — (지급일, 못 정한 이유).

    급여 자료에 지급일이 있으면 그 값(모두 같아야 함), 없으면 거래처 급여지급일 설정으로 계산.
    """
    dates = set(
        (
            await db.execute(
                select(PayrollEntry.payment_date).where(
                    PayrollEntry.monthly_filing_id == filing_id,
                    PayrollEntry.client_id == client_id,
                    PayrollEntry.payment_date.is_not(None),
                    PayrollEntry.deleted.is_(False),
                )
            )
        ).scalars().all()
    )
    if len(dates) > 1:
        return None, "급여 자료의 지급일이 여러 개"
    if dates:
        return dates.pop(), None
    setting = (
        await db.execute(
            select(ClientPayrollDefault).where(ClientPayrollDefault.client_id == client_id)
        )
    ).scalar_one_or_none()
    resolved = (
        resolve_pay_date(period, setting.pay_month_offset, setting.pay_day) if setting else None
    )
    return resolved, None if resolved else "급여지급일 미설정"


# ---------------------------------------------------------------------------
# 전송 작업 등록·조회·취소 (세무사 화면)
# ---------------------------------------------------------------------------


@router.get("/wehago-uploads/preview", response_model=list[WehagoUploadPreviewRow])
async def preview_wehago_uploads(
    filing_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[WehagoUploadPreviewRow]:
    """위하고 전송 전에 거래처별 지급일·차단 사유를 보여 준다. 실제 전송 때 서버가 다시 검사한다."""
    office_id = _office_id(user)
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")
    client_ids = set(
        (
            await db.execute(
                select(PayrollEntry.client_id).where(
                    PayrollEntry.monthly_filing_id == filing.id,
                    PayrollEntry.deleted.is_(False),
                )
            )
        ).scalars().all()
    )
    clients = (
        await db.execute(select(Client).where(Client.id.in_(client_ids)))
    ).scalars().all()
    no_code: dict[str, set[str]] = {}
    for cid, income_type in (
        await db.execute(
            select(PayrollEntry.client_id, PayrollEntry.income_type)
            .outerjoin(Employee, PayrollEntry.employee_id == Employee.id)
            .where(
                PayrollEntry.monthly_filing_id == filing.id,
                func.coalesce(func.trim(Employee.employee_code), "") == "",
                PayrollEntry.deleted.is_(False),
            )
        )
    ).all():
        dtype = "OTHER" if income_type == IncomeType.RETIREMENT else income_type.value
        no_code.setdefault(cid, set()).add(dtype)
    active = set(
        (
            await db.execute(
                select(RpaJob.client_id).where(
                    RpaJob.monthly_filing_id == filing.id,
                    RpaJob.kind.in_(WEHAGO_INPUT_KINDS),
                    RpaJob.status.in_(ACTIVE_STATUSES),
                )
            )
        ).scalars().all()
    )

    # 소득유형별 상태 (근로/사업/기타/일용) — 선택용이 아니라 표시용이다 (plan/16 §4-1).
    # 퇴직소득은 화면의 원천세 미리보기와 동일하게 기타소득에 합쳐서 보여준다.
    DISPLAY_TYPES = ["WAGE", "BUSINESS", "OTHER", "DAILY"]

    # "전송 완료" 판정에 명세서 추가입력(게이트2 마감)을 포함 — 근로소득은 자료입력만으로
    # 충분하지만, 사업소득은 close_business_income_report의 "새로불러오기"가 명세서
    # 추가입력을 충족한다고 보고 그 단계가 실제 성공했는지까지 확인한다 (2026-10-01 결정,
    # §12-2-1·§4-1). 기타·일용은 자료입력 자체가 아직 게이트1에 안 묶여 있어 늘 False.
    succeeded_input_kinds: dict[str, set[RpaJobKind]] = {}
    for j in (
        await db.execute(
            select(RpaJob).where(
                RpaJob.monthly_filing_id == filing.id,
                RpaJob.kind.in_(WEHAGO_INPUT_KINDS),
                RpaJob.status == RpaJobStatus.SUCCEEDED,
            )
        )
    ).scalars().all():
        succeeded_input_kinds.setdefault(j.client_id, set()).add(j.kind)

    latest_production_step: dict[str, dict] = {}
    for j in (
        await db.execute(
            select(RpaJob)
            .where(
                RpaJob.monthly_filing_id == filing.id,
                RpaJob.kind == RpaJobKind.MONTHLY_PRODUCTION,
                RpaJob.status == RpaJobStatus.SUCCEEDED,
            )
            .order_by(RpaJob.created_at.desc())
        )
    ).scalars().all():
        latest_production_step.setdefault(j.client_id, j.step_progress or {})

    # None이면 자료입력(게이트1) 성공만으로 완료, 문자열이면 그 step_progress 키도 "done"이어야 완료.
    # OTHER는 "wehago_other_income" 키를 미리 걸어두지만 아직 그 게이트2 자동화(거주자
    # 기타소득간이지급명세서, plan/16 §13-3-3)가 없어 이 키는 영영 "done"이 안 된다 — 즉
    # 기타소득은 자료입력이 끝나도 "전송완료"가 절대 안 뜨고 "자료입력완료"에 머문다,
    # 명세서 자동화가 생기기 전까지는 의도된 동작이다(§4-1 "명세서 추가입력까지 완료").
    _PRODUCTION_STEP_BY_TYPE: dict[str, str | None] = {
        "WAGE": None, "BUSINESS": "wehago_business_income", "OTHER": "wehago_other_income",
    }
    income_rows = (
        await db.execute(
            select(PayrollEntry.client_id, PayrollEntry.income_type, PayrollEntry.approved).where(
                PayrollEntry.monthly_filing_id == filing.id,
                PayrollEntry.deleted.is_(False),
            )
        )
    ).all()
    breakdown: dict[str, dict[str, list[bool]]] = {}
    for cid, income_type, approved in income_rows:
        dtype = "OTHER" if income_type == IncomeType.RETIREMENT else income_type.value
        breakdown.setdefault(cid, {}).setdefault(dtype, []).append(approved)

    rows = []
    for c in clients:
        pay_date, reason = await _pay_date(db, filing.id, c.id, filing.period)
        client_breakdown = breakdown.get(c.id, {})
        income_types = []
        for t in DISPLAY_TYPES:
            input_kind = INPUT_JOB_KIND_BY_INCOME_TYPE.get(IncomeType[t])
            input_done = input_kind is not None and input_kind in succeeded_input_kinds.get(c.id, set())
            step_key = _PRODUCTION_STEP_BY_TYPE.get(t)
            filing_complete = (
                input_done if step_key is None
                else input_done and latest_production_step.get(c.id, {}).get(step_key) == "done"
            )
            income_types.append(
                IncomeTypeStatus(
                    income_type=t,
                    count=len(client_breakdown.get(t, [])),
                    unapproved_count=sum(1 for a in client_breakdown.get(t, []) if not a),
                    automated=IncomeType[t] in AUTOMATED_INCOME_TYPES,
                    filing_complete=filing_complete,
                )
            )
        if not (c.business_number or "").strip():
            reason = "사업자번호 없음"
        elif c.id in no_code:
            labels = "·".join(_INCOME_TYPE_LABEL[IncomeType[t]] for t in sorted(no_code[c.id]))
            reason = f"위하고 사원코드 없는 사원 있음 ({labels})"
        elif c.id in active:
            reason = "이미 전송 대기·진행 중"
        elif any(not s.automated and s.count > 0 for s in income_types):
            labels = "·".join(
                _INCOME_TYPE_LABEL[IncomeType[s.income_type]]
                for s in income_types if not s.automated and s.count > 0
            )
            reason = f"{labels} 자동화 미지원"
        rows.append(
            WehagoUploadPreviewRow(
                client_id=c.id, pay_date=pay_date, blocked_reason=reason, income_types=income_types,
            )
        )
    return rows


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
            select(PayrollEntry.client_id, PayrollEntry.approved, PayrollEntry.income_type).where(
                PayrollEntry.monthly_filing_id == filing.id,
                PayrollEntry.client_id.in_(client_ids),
                PayrollEntry.deleted.is_(False),
            )
        )
    ).all()
    unapproved = {cid for cid, approved, _ in rows if not approved}
    if unapproved:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"미승인 자료가 있는 거래처는 전송할 수 없습니다: {names(unapproved)}. "
            "먼저 검증·승인을 완료하세요.",
        )
    empty = set(client_ids) - {cid for cid, _, _ in rows}
    if empty:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"자료가 없는 거래처는 전송할 수 없습니다: {names(empty)}."
        )

    # 소득유형별 원자적 전송 (plan/16 §4-1, 2026-09-28) — 신고서 한 장에 전 소득유형이 합산되므로
    # 자동화가 없는 소득유형(사업·기타·일용)에 데이터가 있으면 그 거래처 전체를 전송하지 않는다.
    unautomated_types: dict[str, set[IncomeType]] = {}
    for cid, _approved, income_type in rows:
        if income_type not in AUTOMATED_INCOME_TYPES:
            unautomated_types.setdefault(cid, set()).add(income_type)
    if unautomated_types:
        detail = ", ".join(
            f"{by_id[cid].business_name}({'·'.join(_INCOME_TYPE_LABEL[t] for t in sorted(types, key=str))})"
            for cid, types in unautomated_types.items()
        )
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"자동화가 아직 없는 소득유형이 있어 전송할 수 없습니다: {detail}. "
            "해당 소득은 당분간 수동으로 처리하고, 근로소득만 있는 거래처부터 전송하세요.",
        )

    # 위하고는 사원코드로 사원을 연결한다 — 코드가 없으면 다른 사원에게 급여가 들어갈 수 있다.
    no_code = (
        await db.execute(
            select(PayrollEntry.raw_name, Employee.name)
            .outerjoin(Employee, PayrollEntry.employee_id == Employee.id)
            .where(
                PayrollEntry.monthly_filing_id == filing.id,
                PayrollEntry.client_id.in_(client_ids),
                func.coalesce(func.trim(Employee.employee_code), "") == "",
                PayrollEntry.deleted.is_(False),
            )
        )
    ).all()
    if no_code:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "위하고 사원코드가 없는 사원이 있어 전송할 수 없습니다: "
            f"{', '.join(emp_name or raw for raw, emp_name in no_code)}. "
            "사원 정보에 위하고 사원코드를 입력하세요.",
        )

    # 위하고 급여자료입력은 귀속연월·지급일로 조회한다 — 지급일을 못 정하면 올릴 수 없다.
    no_pay_date = []
    for c in ordered:
        _, reason = await _pay_date(db, filing.id, c.id, filing.period)
        if reason:
            no_pay_date.append(f"{c.business_name}({reason})")
    if no_pay_date:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"지급일을 정할 수 없어 위하고로 전송할 수 없습니다: {', '.join(no_pay_date)}. "
            "거래처 급여 기본값에서 급여지급일을 설정하세요.",
        )

    active = set(
        (
            await db.execute(
                select(RpaJob.client_id).where(
                    RpaJob.monthly_filing_id == filing.id,
                    RpaJob.client_id.in_(client_ids),
                    RpaJob.kind.in_(WEHAGO_INPUT_KINDS),
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

    # 화면(소득유형)마다 자동입력 job이 따로 필요하다 — 근로만 있으면 1개, 근로+사업이면 2개.
    automated_types_by_client: dict[str, set[IncomeType]] = {}
    for cid, _approved, income_type in rows:
        if income_type in AUTOMATED_INCOME_TYPES:
            automated_types_by_client.setdefault(cid, set()).add(income_type)

    jobs = [
        RpaJob(
            tax_office_id=office_id,
            kind=INPUT_JOB_KIND_BY_INCOME_TYPE[income_type],
            status=RpaJobStatus.PENDING,
            monthly_filing_id=filing.id,
            client_id=c.id,
            period=filing.period,
            business_number=c.business_number.strip(),
            business_name=c.business_name,
            requested_by_user_id=user.id,
        )
        for c in ordered
        for income_type in sorted(automated_types_by_client.get(c.id, set()), key=str)
    ]
    db.add_all(jobs)
    await db.commit()
    for job in jobs:
        await db.refresh(job)
    return jobs


@router.get("/jobs", response_model=list[RpaJobOut])
async def list_jobs(
    filing_id: str | None = None,
    unacknowledged: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RpaJob]:
    office_id = _office_id(user)
    query = select(RpaJob).where(RpaJob.tax_office_id == office_id)
    if filing_id:
        query = query.where(RpaJob.monthly_filing_id == filing_id)
    if unacknowledged:  # 하단 작업바 — 진행중 + 끝났지만 아직 [확인] 안 한 작업
        query = query.where(RpaJob.acknowledged_at.is_(None))
    rows = await db.execute(query.order_by(RpaJob.created_at.desc()).limit(200))
    return list(rows.scalars().all())


@router.get("/jobs/activity", response_model=list[RpaActivityJobOut])
async def list_activity(
    scope: Literal["all", "mine"] = "mine",
    unacknowledged: bool = False,
    today: bool = False,
    days: int | None = Query(default=None, ge=1, le=31),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RpaActivityJobOut]:
    """하단 작업바 — 전체작업(사무소 직원 전체)·내작업. 다른 직원 작업은 직원 이름·업무 종류만.

    today: 대기·진행 중 + 오늘(한국 시간) 끝난 작업만 — 작업바 칩.
    days: 최근 N일 안에 요청된 작업 — [내역보기] (3·7·30일).
    """
    office_id = _office_id(user)
    query = select(RpaJob).where(RpaJob.tax_office_id == office_id)
    if scope == "mine":
        query = query.where(RpaJob.requested_by_user_id == user.id)
    if unacknowledged:
        query = query.where(RpaJob.acknowledged_at.is_(None))
    if today:
        midnight = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        query = query.where(or_(RpaJob.status.in_(ACTIVE_STATUSES), RpaJob.finished_at >= midnight))
    if days:
        query = query.where(RpaJob.created_at >= _utcnow() - timedelta(days=days))
    jobs = (await db.execute(query.order_by(RpaJob.created_at.desc()).limit(500))).scalars().all()
    names = dict(
        (
            await db.execute(
                select(User.id, User.name).where(User.id.in_({j.requested_by_user_id for j in jobs}))
            )
        ).all()
    )
    out = []
    for job in jobs:
        mine = job.requested_by_user_id == user.id
        row = RpaActivityJobOut.model_validate(
            {
                **RpaJobOut.model_validate(job).model_dump(),
                "requested_by_name": names.get(job.requested_by_user_id),
                "is_mine": mine,
            }
        )
        if not mine:
            row = row.model_copy(
                update=dict.fromkeys(
                    (
                        "monthly_filing_id", "client_id", "period", "business_number", "business_name",
                        "result_message", "step_progress", "compare_diff",
                    )
                )
            )
        out.append(row)
    return out


@router.post("/jobs/{job_id}/cancel", response_model=RpaJobOut)
async def cancel_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RpaJob:
    """PENDING은 그냥 취소. RUNNING은 "강제 중지" — 서버 기록만 즉시 FAILED로 바꿔
    뒤에 막힌 작업 큐를 풀어준다. 에이전트는 서버에 접속할 수 없고(폴링 전용, claim_job의
    15분 타임아웃 처리와 같은 제약) 자동화 단계 사이 중지요청을 확인하는 지점도 아직 없어,
    이미 위하고에서 진행 중인 브라우저 자동화 자체를 중간에 멈추지는 못한다 — 프론트에서
    이 제약을 사용자에게 먼저 안내한 뒤 호출한다.
    """
    office_id = _office_id(user)
    job = await db.get(RpaJob, job_id)
    if not job or job.tax_office_id != office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작업을 찾을 수 없습니다")

    if job.status == RpaJobStatus.PENDING:
        new_status: RpaJobStatus = RpaJobStatus.CANCELED
        message = None
    elif job.status == RpaJobStatus.RUNNING:
        new_status = RpaJobStatus.FAILED
        message = (
            "사용자가 강제 중지했습니다. 자동화 PC가 이미 위하고에서 작업 중이었다면 "
            "그 화면 조작은 서버와 별개로 계속되거나 끝날 수 있습니다."
        )
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, "대기 중이거나 진행 중인 작업만 중지할 수 있습니다")

    values: dict = {"status": new_status, "finished_at": _utcnow()}
    if message is not None:
        values["result_message"] = message
    result = await db.execute(
        update(RpaJob).where(RpaJob.id == job_id, RpaJob.status == job.status).values(**values)
    )
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "작업 상태가 바뀌어 중지하지 못했습니다. 다시 시도하세요")
    await db.commit()
    await db.refresh(job)
    return job


@router.post("/jobs/{job_id}/acknowledge", response_model=RpaJobOut)
async def acknowledge_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RpaJob:
    """하단 작업바 [확인] — 끝난 작업을 바에서 내린다. 진행 중인 작업은 내릴 수 없다."""
    office_id = _office_id(user)
    job = await db.get(RpaJob, job_id)
    if not job or job.tax_office_id != office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "작업을 찾을 수 없습니다")
    if job.status in (RpaJobStatus.PENDING, RpaJobStatus.RUNNING):
        raise HTTPException(status.HTTP_409_CONFLICT, "진행 중인 작업은 확인 처리할 수 없습니다")
    if job.acknowledged_at is None:
        job.acknowledged_at = _utcnow()
        await db.commit()
        await db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# 에이전트 전용 (X-Agent-Token)
# ---------------------------------------------------------------------------


async def next_fair_job_id(db: AsyncSession, office_id: str, kind_filter: ColumnElement[bool]) -> str | None:
    """다음에 돌릴 대기 작업 — 직원별로 한 건씩 돌아가며.

    대기 작업이 있는 직원 중 이 대기열에서 마지막으로 작업이 시작된 지 가장 오래된 직원
    (한 번도 없으면 맨 앞)을 고르고, 그 직원의 가장 먼저 요청한 작업을 준다.
    한 직원의 요청 순서는 그대로 지켜진다.
    """
    scope = (RpaJob.tax_office_id == office_id, kind_filter)
    pending = (
        await db.execute(
            select(RpaJob.requested_by_user_id, func.min(RpaJob.created_at))
            .where(*scope, RpaJob.status == RpaJobStatus.PENDING)
            .group_by(RpaJob.requested_by_user_id)
        )
    ).all()
    if not pending:
        return None
    last_claimed = dict(
        (
            await db.execute(
                select(RpaJob.requested_by_user_id, func.max(RpaJob.claimed_at))
                .where(*scope, RpaJob.requested_by_user_id.in_([u for u, _ in pending]))
                .group_by(RpaJob.requested_by_user_id)
            )
        ).all()
    )
    user_id, _ = min(
        pending,
        key=lambda row: (
            last_claimed.get(row[0]) is not None,
            _as_utc(last_claimed[row[0]]) if last_claimed.get(row[0]) else row[1],
            row[1],
        ),
    )
    return (
        await db.execute(
            select(RpaJob.id)
            .where(*scope, RpaJob.status == RpaJobStatus.PENDING, RpaJob.requested_by_user_id == user_id)
            .order_by(RpaJob.created_at)
            .limit(1)
        )
    ).scalar_one()


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
                RpaJob.kind.in_(WEHAGO_JOB_KINDS),
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

    # 증명원은 /certificates/agent/claim
    next_id = await next_fair_job_id(db, agent.tax_office_id, RpaJob.kind.in_(WEHAGO_JOB_KINDS))
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
    out = RpaJobOut.model_validate(job)
    if job.kind == RpaJobKind.WEHAGO_PAYROLL_INPUT and job.monthly_filing_id and job.client_id:
        out.pay_date, _ = await _pay_date(db, job.monthly_filing_id, job.client_id, job.period)
    return RpaClaimOut(job=out)


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
                    # 급여자료입력(SmartA SWSA0101)은 근로소득 전용 — 사업·기타·일용은 다른 화면(§13-3)이라
                    # 여기 섞이면 안 된다. create_wehago_uploads가 미리 막지만, 방어적으로 한 번 더 거른다.
                    PayrollEntry.income_type == IncomeType.WAGE,
                    # 소프트 삭제된 항목이 실제 위하고 업로드 엑셀에 들어가면 안 된다 (신고 사고).
                    PayrollEntry.deleted.is_(False),
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

    try:
        blob = generate_payroll_excel(entries, period=job.period, client_name=job.business_name)
    except PayrollExcelError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    agent.last_seen_at = _utcnow()
    await db.commit()
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="payroll_{job.period}.xlsx"'},
    )


@router.get("/agent/jobs/{job_id}/business-income-excel")
async def agent_download_business_income_excel(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    agent: RpaAgent = Depends(get_current_agent),
) -> Response:
    """사업소득자료입력(SmartA SWBU0102) 업로드용 엑셀 — `agent_download_payroll_excel`과 같은 구조."""
    job = await _agent_running_job(db, agent, job_id)
    entries = list(
        (
            await db.execute(
                select(PayrollEntry)
                .where(
                    PayrollEntry.monthly_filing_id == job.monthly_filing_id,
                    PayrollEntry.client_id == job.client_id,
                    PayrollEntry.income_type == IncomeType.BUSINESS,
                    PayrollEntry.deleted.is_(False),
                )
                .options(selectinload(PayrollEntry.employee))
            )
        )
        .scalars()
        .all()
    )
    if not entries:
        raise HTTPException(status.HTTP_409_CONFLICT, "자료가 없습니다.")
    if any(not e.approved for e in entries):
        raise HTTPException(status.HTTP_409_CONFLICT, "미승인 자료가 있어 업로드할 수 없습니다.")

    # 사업소득은 수동입력 화면에 지급일 칸이 없어 entry.payment_date가 거의 항상 비어 있다 —
    # 거래처 급여지급일 기본값(근로소득과 동일 계산)을 엑셀 생성 시 기본값으로 채운다.
    default_payment_date, _ = await _pay_date(db, job.monthly_filing_id, job.client_id, job.period)
    blob = generate_smarta_business_xls(entries, period=job.period, default_payment_date=default_payment_date)
    agent.last_seen_at = _utcnow()
    await db.commit()
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="business_income_{job.period}.xlsx"'},
    )


@router.get("/agent/jobs/{job_id}/other-income-excel")
async def agent_download_other_income_excel(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    agent: RpaAgent = Depends(get_current_agent),
) -> Response:
    """기타소득자료입력(SmartA SWET0102) 업로드용 엑셀 — `agent_download_business_income_excel`과 같은 구조.

    소득구분코드(76·79 등)가 없거나 `RESIDENT_INCOME_CODE_LABELS`에 없는 항목은 위하고가
    인식 못 해 생성기가 조용히 건너뛴다(plan/16 §13-3-3) — 전부 건너뛰면 빈 엑셀을 올리게
    되므로 여기서 미리 걸러 409로 막는다.
    """
    job = await _agent_running_job(db, agent, job_id)
    entries = list(
        (
            await db.execute(
                select(PayrollEntry)
                .where(
                    PayrollEntry.monthly_filing_id == job.monthly_filing_id,
                    PayrollEntry.client_id == job.client_id,
                    PayrollEntry.income_type == IncomeType.OTHER,
                    PayrollEntry.deleted.is_(False),
                )
                .options(selectinload(PayrollEntry.employee))
            )
        )
        .scalars()
        .all()
    )
    if not entries:
        raise HTTPException(status.HTTP_409_CONFLICT, "자료가 없습니다.")
    if any(not e.approved for e in entries):
        raise HTTPException(status.HTTP_409_CONFLICT, "미승인 자료가 있어 업로드할 수 없습니다.")
    if not any(e.other_income_code in RESIDENT_INCOME_CODE_LABELS for e in entries):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "소득구분코드가 입력된 기타소득 자료가 없어 업로드할 수 없습니다. "
            "사원 정보에서 소득구분을 입력하세요.",
        )

    blob = generate_smarta_other_income_xls(entries, period=job.period)
    agent.last_seen_at = _utcnow()
    await db.commit()
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="other_income_{job.period}.xlsx"'},
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
    if payload.step_progress is not None:
        job.step_progress = payload.step_progress
    if payload.compare_diff is not None:
        job.compare_diff = payload.compare_diff

    # 자동입력이 끝났거나 (게이트 2 알림), MONTHLY_PRODUCTION이 끝났으면 (게이트 3 알림) — 요청자에게 알림.
    _notify_gate_transition(db, job)

    await db.commit()
    await db.refresh(job)
    return job


def _notify_gate_transition(db: AsyncSession, job: RpaJob) -> None:
    """게이트 사이 전이가 발생했을 때 알림을 큐에 넣는다.

    - 게이트 1 자동입력(WEHAGO_INPUT_KINDS) SUCCEEDED → 게이트 2 검토 알림 (거래처가 근로+사업
      둘 다 있으면 각 kind가 끝날 때마다 한 번씩 온다 — 중복이지만 해롭지 않다)
    - MONTHLY_PRODUCTION SUCCEEDED → 게이트 3 발송 확정 알림 (실제 filing_result_id는 filing-result 등록 후 채워짐)
    - 어느 kind든 FAILED → 실패 알림
    """
    if job.status == RpaJobStatus.SUCCEEDED and job.kind in WEHAGO_INPUT_KINDS:
        notification_kind = RpaNotificationKind.GATE2_REVIEW
        title = f"[{job.business_name}] 위하고 자동입력 완료 — 급여명세서 검토·제작 필요"
        guide = "위하고에 급여자료가 입력되었습니다. 이지원천에서 명세서를 검토한 뒤 '제작' 버튼을 눌러주세요."
    elif job.status == RpaJobStatus.SUCCEEDED and job.kind == RpaJobKind.MONTHLY_PRODUCTION:
        notification_kind = RpaNotificationKind.GATE3_PUBLISH
        title = f"[{job.business_name}] 홈택스·위택스 신고 완료 — 접수증 검토·발송 확정 필요"
        guide = "접수증·납부서를 확인한 뒤 '발송 확정' 버튼을 눌러 사장님 포털·문자를 발송하세요."
    elif job.status == RpaJobStatus.SUCCEEDED and job.kind in WEHAGO_IMPORT_KINDS:
        notification_kind = RpaNotificationKind.IMPORT_DONE
        title = f"[{job.business_name}] 위하고 가져오기 완료"
        guide = "위하고 수임처·사원 기본사항을 가져왔습니다. 값이 달라 덮어쓰지 않은 항목은 가져오기 결과에서 확인하세요."
    elif job.status == RpaJobStatus.FAILED:
        notification_kind = RpaNotificationKind.FAILURE
        title = f"[{job.business_name}] {job.kind.value} 실패"
        guide = "작업이 실패했습니다. 로그를 확인하고 필요 시 수동 처리하세요."
    else:
        return
    # 사용자 안내 + 에이전트 회신 메시지를 함께 남긴다 — 사용자에게 늘 다음 액션이 보여야 한다.
    body = f"{guide}\n\n{job.result_message}" if job.result_message else guide
    db.add(
        RpaNotification(
            tax_office_id=job.tax_office_id,
            recipient_user_id=job.requested_by_user_id,
            kind=notification_kind,
            title=title,
            body=body,
            job_id=job.id,
        )
    )


# ---------------------------------------------------------------------------
# 게이트 2: '제작' 버튼 — 위하고 마감·제작 + 홈택스·위택스 일괄 작업 등록 (사무소 사용자)
# ---------------------------------------------------------------------------


@router.post("/productions", response_model=list[RpaJobOut], status_code=status.HTTP_201_CREATED)
async def create_productions(
    payload: ProductionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RpaJob]:
    """자동입력 ✅ 거래처만 대상으로 위하고 마감·제작 + 홈택스·위택스 신고를 일괄 등록.

    한 거래처가 실패해도 다른 거래처는 계속 진행된다 (에이전트 로직, §4-2).
    """
    office_id = _office_id(user)
    filing = await db.get(MonthlyFiling, payload.filing_id)
    if not filing or filing.tax_office_id != office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")

    client_ids = list(dict.fromkeys(payload.client_ids))

    # 자동입력이 성공한 거래처만 [제작]에 태울 수 있다 — 근로+사업 둘 다 있는 거래처는
    # 두 kind 모두 성공해야 한다. 하나만 확인하면 아직 안 올라간 소득을 마감해 버리는
    # 사고가 난다(plan/16 §13-3-4).
    income_rows = (
        await db.execute(
            select(PayrollEntry.client_id, PayrollEntry.income_type).where(
                PayrollEntry.monthly_filing_id == filing.id,
                PayrollEntry.client_id.in_(client_ids),
                PayrollEntry.deleted.is_(False),
            )
        )
    ).all()
    expected_kinds_by_client: dict[str, set[RpaJobKind]] = {}
    for cid, income_type in income_rows:
        if income_type in AUTOMATED_INCOME_TYPES:
            expected_kinds_by_client.setdefault(cid, set()).add(INPUT_JOB_KIND_BY_INCOME_TYPE[income_type])

    input_jobs = (
        await db.execute(
            select(RpaJob).where(
                RpaJob.monthly_filing_id == filing.id,
                RpaJob.client_id.in_(client_ids),
                RpaJob.kind.in_(WEHAGO_INPUT_KINDS),
            )
        )
    ).scalars().all()
    latest_succeeded: dict[tuple[str, RpaJobKind], RpaJob] = {}
    for j in input_jobs:
        if j.status != RpaJobStatus.SUCCEEDED:
            continue
        key = (j.client_id, j.kind)
        existing = latest_succeeded.get(key)
        if existing is None or _as_utc(j.created_at) > _as_utc(existing.created_at):
            latest_succeeded[key] = j

    input_by_client: dict[str, RpaJob] = {}
    missing: list[str] = []
    for cid in client_ids:
        expected = expected_kinds_by_client.get(cid, set())
        succeeded = [latest_succeeded[(cid, k)] for k in expected if (cid, k) in latest_succeeded]
        if not expected or len(succeeded) != len(expected):
            missing.append(cid)
        else:
            input_by_client[cid] = succeeded[0]
    if missing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"위하고 자동입력이 완료되지 않은 거래처가 있습니다 (client_ids: {missing}). "
            "먼저 '위하고 전송'을 완료하세요.",
        )

    active = set(
        (
            await db.execute(
                select(RpaJob.client_id).where(
                    RpaJob.monthly_filing_id == filing.id,
                    RpaJob.client_id.in_(client_ids),
                    RpaJob.kind == RpaJobKind.MONTHLY_PRODUCTION,
                    RpaJob.status.in_(ACTIVE_STATUSES),
                )
            )
        ).scalars().all()
    )
    if active:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"이미 제작이 대기·진행 중인 거래처입니다 (client_ids: {sorted(active)}).",
        )

    jobs = [
        RpaJob(
            tax_office_id=office_id,
            kind=RpaJobKind.MONTHLY_PRODUCTION,
            status=RpaJobStatus.PENDING,
            monthly_filing_id=filing.id,
            client_id=cid,
            period=filing.period,
            business_number=input_by_client[cid].business_number,
            business_name=input_by_client[cid].business_name,
            requested_by_user_id=user.id,
        )
        for cid in client_ids
    ]
    db.add_all(jobs)
    await db.commit()
    for job in jobs:
        await db.refresh(job)
    return jobs


# ---------------------------------------------------------------------------
# 에이전트: 접수증·납부서 등록 (MONTHLY_PRODUCTION 작업 중)
# ---------------------------------------------------------------------------


@router.post("/agent/jobs/{job_id}/filing-result", response_model=FilingResultOut)
async def agent_register_filing_result(
    job_id: str,
    payload: AgentFilingResultIn,
    db: AsyncSession = Depends(get_db),
    agent: RpaAgent = Depends(get_current_agent),
) -> ClientFilingResult:
    """에이전트가 홈택스·위택스 접수증·납부서를 서버에 등록.

    이 시점에는 `published_at=NULL` (비공개). 로그인 사용자가 '발송 확정'을 클릭한 뒤에만
    사장님 포털·문자로 나간다 (§4-5·§4-6).
    """
    job = await _agent_running_job(db, agent, job_id)
    if job.kind != RpaJobKind.MONTHLY_PRODUCTION:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "MONTHLY_PRODUCTION 작업에서만 신고결과를 등록할 수 있습니다",
        )
    if payload.client_id != job.client_id or payload.period != job.period:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "요청의 client_id·period가 작업과 일치하지 않습니다 (엉뚱한 거래처 방지)",
        )

    existing = (
        await db.execute(
            select(ClientFilingResult).where(
                ClientFilingResult.client_id == payload.client_id,
                ClientFilingResult.period == payload.period,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = ClientFilingResult(
            client_id=payload.client_id,
            period=payload.period,
            source=FilingResultSource.RPA,
        )
        db.add(existing)
    else:
        # 재실행으로 두 번 등록되면 최근 값으로 덮어쓰되 이미 발송 확정된 경우엔 거부한다.
        if existing.published_at is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "이미 발송 확정된 신고결과가 있습니다 — 수정하려면 발송 확정을 취소하세요",
            )

    existing.settled_tax = payload.settled_tax
    existing.virtual_account = payload.virtual_account
    existing.epayment_number = payload.epayment_number
    existing.due_date = payload.due_date
    existing.receipt_key = payload.receipt_key
    existing.receipt_name = payload.receipt_name
    existing.payment_slip_key = payload.payment_slip_key
    existing.payment_slip_name = payload.payment_slip_name
    existing.source = FilingResultSource.RPA

    agent.last_seen_at = _utcnow()
    await db.commit()
    await db.refresh(existing)
    return existing


# ---------------------------------------------------------------------------
# 게이트 3: '발송 확정' — 사장님 포털 공개 + 납부안내 문자 트리거
# ---------------------------------------------------------------------------


@router.post(
    "/filing-results/{filing_result_id}/publish", response_model=PublishFilingResultOut
)
async def publish_filing_result(
    filing_result_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ClientFilingResult:
    """게이트 3 — 접수증·납부서를 검토한 뒤 사장님 포털·문자 발송을 트리거한다."""
    office_id = _office_id(user)
    result = await db.get(ClientFilingResult, filing_result_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "신고결과를 찾을 수 없습니다")
    client = await db.get(Client, result.client_id)
    if client is None or client.tax_office_id != office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "신고결과를 찾을 수 없습니다")

    if result.published_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 발송 확정된 신고결과입니다")

    # 검토 최소 조건: 접수증 또는 납부세액이 있어야 발송 확정 가능
    if not result.receipt_key and result.settled_tax is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "접수증·납부세액이 등록되지 않아 발송 확정할 수 없습니다",
        )

    result.published_at = _utcnow()
    result.confirmed_by_user_id = user.id

    # 하단 작업바: 이 신고의 제작 작업에 '납부서 전송완료' 단계를 남기고 바에 다시 올린다
    job = (
        await db.execute(
            select(RpaJob)
            .where(
                RpaJob.client_id == result.client_id,
                RpaJob.period == result.period,
                RpaJob.kind == RpaJobKind.MONTHLY_PRODUCTION,
            )
            .order_by(RpaJob.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if job is not None:
        job.step_progress = {**(job.step_progress or {}), "published": "done"}
        job.acknowledged_at = None
    # 실제 문자 발송은 별도 서비스(13-messaging-activation.md 전제) — 여기선 flag만 세팅
    await db.commit()
    await db.refresh(result)
    return result


# ---------------------------------------------------------------------------
# 알림 조회·읽음 처리
# ---------------------------------------------------------------------------


@router.get("/notifications", response_model=list[RpaNotificationOut])
async def list_notifications(
    unread_only: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RpaNotification]:
    query = select(RpaNotification).where(RpaNotification.recipient_user_id == user.id)
    if unread_only:
        query = query.where(RpaNotification.read_at.is_(None))
    rows = await db.execute(query.order_by(RpaNotification.created_at.desc()).limit(100))
    return list(rows.scalars().all())


@router.post("/notifications/{notification_id}/read", response_model=RpaNotificationOut)
async def mark_notification_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RpaNotification:
    n = await db.get(RpaNotification, notification_id)
    if n is None or n.recipient_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "알림을 찾을 수 없습니다")
    if n.read_at is None:
        n.read_at = _utcnow()
        await db.commit()
        await db.refresh(n)
    return n
