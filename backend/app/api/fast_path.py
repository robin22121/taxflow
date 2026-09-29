"""전월 동일 페스트패스 (plan/01-workflow-roadmap.md §1.3).

정상 케이스에서 [5]~[8] 단계를 원클릭으로 압축한다:
- 전월 PayrollEntry를 이번 달 필링으로 복사하되 **최신 세율로 재계산**
- 원천세 합계 델타가 임계치(±2%) 이내면 자동 승인 → 위하고 전송 큐잉 준비
- 초과하면 커밋 거부 → 프론트가 기존 [5] 검증·승인 화면으로 폴백

`carry_forward` 프리뷰(collect.py:321)와 다른 점:
- 최신 세율·부양가족 값으로 income_tax/local_tax를 **재계산**해서 저장 (carry_forward는 전월 확정치 그대로 사용)
- 델타 임계치 게이트를 백엔드에서 강제
- 세션 미존재 시 자동 생성 (외부 자료 없이 세무사 원클릭으로 진입)
"""

from __future__ import annotations

from datetime import UTC
from datetime import datetime as _dt

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models import (
    Client,
    CollectionEvent,
    CollectionSessionStatus,
    Employee,
    EmploymentStatus,
    MonthlyFiling,
    PayrollEntry,
    User,
)
from app.models.payroll import MatchStatus
from app.services.invite import get_or_create_session
from app.services.tax_calc import calculate_withholding_tax, income_type_to_a_code

router = APIRouter()


DEFAULT_THRESHOLD_PCT = 2.0


def _prev_period(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


class FastPathRow(BaseModel):
    """페스트패스 요약용 직원별 행."""

    employee_id: str | None
    raw_name: str
    income_type: str
    total_amount: int
    non_taxable: int
    taxable: int
    income_tax_prev: int
    income_tax_curr: int
    local_tax_prev: int
    local_tax_curr: int


class FastPathSummary(BaseModel):
    """전월 동일 페스트패스 요약 카드 데이터 (plan/01 §1.3 요약 카드 사양)."""

    client_id: str
    client_name: str
    prev_period: str
    curr_period: str
    person_count: int
    resigned_excluded: int
    total_pay: int
    withholding_prev: int
    withholding_curr: int
    local_tax_prev: int
    local_tax_curr: int
    # 원천세 합계 기준 델타 — abs(curr - prev) / prev
    delta_pct: float
    threshold_pct: float
    within_threshold: bool
    # 커밋 가능 여부 (동일 필링에 이미 항목이 있으면 False → 프론트는 [5] 검토 화면으로 유도)
    can_commit: bool
    blocker: str | None
    rows: list[FastPathRow]


class FastPathCommitIn(BaseModel):
    threshold_pct: float = Field(default=DEFAULT_THRESHOLD_PCT, ge=0.0, le=100.0)


class FastPathCommitOut(BaseModel):
    session_id: str
    created_entries: int
    withholding_curr: int
    local_tax_curr: int
    delta_pct: float
    approved: bool


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


async def _load_scope(
    db: AsyncSession, filing_id: str, client_id: str, user: User
) -> tuple[MonthlyFiling, Client]:
    filing = await db.get(MonthlyFiling, filing_id)
    if not filing or filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Filing not found")
    client = await db.get(Client, client_id)
    if not client or client.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return filing, client


async def _load_prev_entries(
    db: AsyncSession, client: Client, filing: MonthlyFiling
) -> tuple[list[PayrollEntry], str]:
    prev_period = _prev_period(filing.period)
    rows = (
        await db.execute(
            select(PayrollEntry)
            .join(MonthlyFiling, PayrollEntry.monthly_filing_id == MonthlyFiling.id)
            .where(
                MonthlyFiling.tax_office_id == filing.tax_office_id,
                MonthlyFiling.period == prev_period,
                PayrollEntry.client_id == client.id,
                PayrollEntry.deleted.is_(False),
            )
        )
    ).scalars().all()
    return list(rows), prev_period


async def _active_employees(
    db: AsyncSession, client_id: str
) -> dict[str, Employee]:
    """재직 중인 직원 마스터 (`id → Employee`). 부양가족·자녀 최신값을 세액 계산에 반영하기 위해 필요."""
    rows = (
        await db.execute(
            select(Employee).where(
                Employee.client_id == client_id,
                Employee.status != EmploymentStatus.RESIGNED,
            )
        )
    ).scalars().all()
    return {e.id: e for e in rows}


async def _current_entry_count(
    db: AsyncSession, filing_id: str, client_id: str
) -> int:
    rows = (
        await db.execute(
            select(PayrollEntry.id).where(
                PayrollEntry.monthly_filing_id == filing_id,
                PayrollEntry.client_id == client_id,
                PayrollEntry.deleted.is_(False),
            )
        )
    ).scalars().all()
    return len(rows)


def _recalc_row(
    entry: PayrollEntry, employee: Employee | None
) -> tuple[int, int, int, int, int]:
    """전월 엔트리를 최신 세율·부양가족 값으로 재계산.

    - taxable = total_amount - non_taxable (전월 값 그대로 씀. 비과세 정책 변경 없음)
    - 부양가족/자녀/조정률: Employee 마스터가 있으면 그 값을 **우선** 사용
      (혼인·출산·부양가족 변경이 반영된다). 마스터 미매칭이면 전월 값 fallback.
    - 최신 세율표(wage_tax_table) + 사업소득 세율은 tax_calc가 latest를 참조

    Returns:
        (income_tax, local_tax, dependents, children, rate_adjust) —
        재계산에 실제로 사용한 값을 함께 반환해 저장 시 그대로 쓸 수 있다.
    """
    taxable = max(0, entry.taxable or 0)
    biz_code = entry.business_type_code
    if employee is not None:
        dependents = employee.dependents_count or 1
        children = employee.children_count or 0
        rate_adjust = employee.withholding_rate_adjust or 100
    else:
        dependents = entry.dependents or 1
        children = entry.children or 0
        rate_adjust = entry.rate_adjust or 100
    tax = calculate_withholding_tax(
        entry.income_type,
        taxable,
        dependents=dependents,
        children=children,
        rate_adjust=rate_adjust,
        business_type_code=biz_code,
    )
    return tax.income_tax, tax.local_tax, dependents, children, rate_adjust


async def _build_summary(
    db: AsyncSession,
    filing: MonthlyFiling,
    client: Client,
    threshold_pct: float,
) -> FastPathSummary:
    prev_entries, prev_period = await _load_prev_entries(db, client, filing)
    if not prev_entries:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{prev_period} 급여자료가 없습니다 — 전월 동일 페스트패스를 사용할 수 없습니다",
        )

    employees = await _active_employees(db, client.id)

    rows: list[FastPathRow] = []
    resigned = 0
    total_pay = 0
    withholding_prev = 0
    withholding_curr = 0
    local_tax_prev = 0
    local_tax_curr = 0
    for pe in prev_entries:
        # 퇴사 처리된 직원은 이월하지 않음 (carry_forward preview와 동일 정책)
        if pe.employee_id and pe.employee_id not in employees:
            resigned += 1
            continue
        curr_income, curr_local, _, _, _ = _recalc_row(
            pe, employees.get(pe.employee_id) if pe.employee_id else None
        )
        prev_income = pe.income_tax or 0
        prev_local = pe.local_tax or 0
        rows.append(
            FastPathRow(
                employee_id=pe.employee_id,
                raw_name=pe.raw_name,
                income_type=pe.income_type.value,
                total_amount=pe.total_amount or 0,
                non_taxable=pe.non_taxable or 0,
                taxable=pe.taxable or 0,
                income_tax_prev=prev_income,
                income_tax_curr=curr_income,
                local_tax_prev=prev_local,
                local_tax_curr=curr_local,
            )
        )
        total_pay += pe.total_amount or 0
        withholding_prev += prev_income
        withholding_curr += curr_income
        local_tax_prev += prev_local
        local_tax_curr += curr_local

    if not rows:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{prev_period} 인원이 모두 퇴사 처리되어 이월할 항목이 없습니다",
        )

    if withholding_prev == 0:
        # 전월 원천세가 0이면 % 델타 정의 불가 — curr이 0이면 델타 0%, 아니면 무한대 취급
        delta_pct = 0.0 if withholding_curr == 0 else 100.0
    else:
        delta_pct = abs(withholding_curr - withholding_prev) / withholding_prev * 100.0

    within = delta_pct <= threshold_pct

    # 커밋 차단 사유
    existing = await _current_entry_count(db, filing.id, client.id)
    blocker: str | None = None
    if existing > 0:
        blocker = f"이번 달({filing.period}) 자료가 이미 {existing}건 있습니다 — 기존 항목을 지운 뒤 다시 시도하세요"

    return FastPathSummary(
        client_id=client.id,
        client_name=client.business_name,
        prev_period=prev_period,
        curr_period=filing.period,
        person_count=len(rows),
        resigned_excluded=resigned,
        total_pay=total_pay,
        withholding_prev=withholding_prev,
        withholding_curr=withholding_curr,
        local_tax_prev=local_tax_prev,
        local_tax_curr=local_tax_curr,
        delta_pct=round(delta_pct, 3),
        threshold_pct=threshold_pct,
        within_threshold=within,
        can_commit=(blocker is None),
        blocker=blocker,
        rows=rows,
    )


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------


@router.post(
    "/{filing_id}/clients/{client_id}/fast-path/preview",
    response_model=FastPathSummary,
)
async def fast_path_preview(
    filing_id: str,
    client_id: str,
    payload: FastPathCommitIn | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FastPathSummary:
    """전월 동일 페스트패스 프리뷰 — DB 미수정.

    프론트는 이 응답으로 요약 카드를 렌더한다. `within_threshold=true`이고
    `can_commit=true`일 때만 [신고 진행] 버튼을 활성화한다.
    """
    filing, client = await _load_scope(db, filing_id, client_id, user)
    threshold = payload.threshold_pct if payload else DEFAULT_THRESHOLD_PCT
    return await _build_summary(db, filing, client, threshold)


@router.post(
    "/{filing_id}/clients/{client_id}/fast-path/commit",
    response_model=FastPathCommitOut,
)
async def fast_path_commit(
    filing_id: str,
    client_id: str,
    payload: FastPathCommitIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FastPathCommitOut:
    """페스트패스 커밋 — 전월 항목을 최신 세율로 재계산한 뒤 approved=True로 저장.

    델타 초과·기존 항목 존재 시 409로 거부 → 프론트는 기존 [5] 검증 화면으로 폴백.
    """
    filing, client = await _load_scope(db, filing_id, client_id, user)
    summary = await _build_summary(db, filing, client, payload.threshold_pct)

    if not summary.can_commit:
        raise HTTPException(status.HTTP_409_CONFLICT, summary.blocker or "커밋 불가")
    if not summary.within_threshold:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"원천세 델타 {summary.delta_pct}% > 임계치 {summary.threshold_pct}% — "
            f"검증·승인 화면에서 개별 확인이 필요합니다",
        )

    prev_entries, _ = await _load_prev_entries(db, client, filing)
    employees = await _active_employees(db, client.id)

    session = await get_or_create_session(db, filing, client)
    session.status = CollectionSessionStatus.RECEIVED
    session.last_response_at = _dt.now(UTC)

    event = CollectionEvent(
        session_id=session.id,
        event_type="fast_path_prev_same",
        channel="fast_path_prev_same",
        raw_text=(
            f"전월({summary.prev_period}) 동일 페스트패스 — {summary.person_count}건 "
            f"(퇴사자 {summary.resigned_excluded}명 제외, 델타 {summary.delta_pct}%)"
        ),
        sender_name=user.email or "fast-path",
    )
    db.add(event)
    await db.flush()

    created = 0
    for pe in prev_entries:
        if pe.employee_id and pe.employee_id not in employees:
            continue
        emp = employees.get(pe.employee_id) if pe.employee_id else None
        income_tax, local_tax, dependents, children, rate_adjust = _recalc_row(pe, emp)
        db.add(
            PayrollEntry(
                monthly_filing_id=filing.id,
                collection_session_id=session.id,
                collection_event_id=event.id,
                client_id=client.id,
                employee_id=pe.employee_id,
                raw_name=pe.raw_name,
                income_type=pe.income_type,
                a_code=income_type_to_a_code(pe.income_type),
                business_type_code=pe.business_type_code,
                total_amount=pe.total_amount or 0,
                salary_amount=pe.salary_amount,
                bonus_amount=pe.bonus_amount,
                non_taxable=pe.non_taxable or 0,
                meal_amount=pe.meal_amount or 0,
                car_amount=pe.car_amount or 0,
                childcare_amount=pe.childcare_amount or 0,
                taxable=pe.taxable or 0,
                national_pension=pe.national_pension or 0,
                health_insurance=pe.health_insurance or 0,
                employment_insurance=pe.employment_insurance or 0,
                longterm_care=pe.longterm_care or 0,
                income_tax=income_tax,
                local_tax=local_tax,
                student_loan=pe.student_loan or 0,
                settlement_insurance=pe.settlement_insurance or 0,
                rent_support=pe.rent_support or 0,
                payment_date=None,
                # 재계산에 실제로 사용한 최신값을 그대로 저장 (Employee 마스터 값 우선)
                dependents=dependents,
                children=children,
                rate_adjust=rate_adjust,
                match_status=MatchStatus.MATCHED if pe.employee_id else MatchStatus.AMBIGUOUS,
                prev_amount=pe.total_amount or 0,
                approved=True,  # 페스트패스 게이트를 통과했으므로 자동 승인
            )
        )
        created += 1

    filing.total_entries = (filing.total_entries or 0) + created
    await db.commit()

    return FastPathCommitOut(
        session_id=session.id,
        created_entries=created,
        withholding_curr=summary.withholding_curr,
        local_tax_curr=summary.local_tax_curr,
        delta_pct=summary.delta_pct,
        approved=True,
    )
