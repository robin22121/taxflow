"""Authenticated collection endpoint — used by the dashboard 'manual paste' UI
and by webhook handlers (kakao/email) after they resolve a tenant.

The full pipeline:
    raw text → AI parser → matching engine → upserts PayrollEntry + (optionally) follow-up.
"""

from __future__ import annotations

from datetime import UTC, date, datetime as _dt

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_user, get_db
from app.models import (
    Client,
    CollectionEvent,
    CollectionSession,
    CollectionSessionStatus,
    Employee,
    EmploymentStatus,
    MonthlyFiling,
    PayrollEntry,
)
from app.models.payroll import IncomeType, MatchStatus
from app.models import User
from app.schemas.filings import (
    CollectCommitIn,
    CollectMessageIn,
    CollectMessageOut,
    CollectPreviewOut,
    ParsedEntryPreview,
)
from app.services.ai_parser import parse_payroll_message
from app.services.file_intake import intake_file
from app.services.matching import (
    EmployeeMaster,
    MatchingResult,
    PayrollEntryCandidate,
    reconcile,
)
from app.services.payroll_defaults import load_payroll_defaults
from app.services.storage import get_storage
from app.services.tax_calc import (
    calculate_withholding_tax,
    income_type_to_a_code,
)

router = APIRouter()


_MAX_UPLOAD_BYTES = 25 * 1024 * 1024


async def _load_session(
    db: AsyncSession, session_id: str, user: User
) -> CollectionSession:
    session = await db.get(
        CollectionSession,
        session_id,
        options=[selectinload(CollectionSession.client), selectinload(CollectionSession.monthly_filing)],
    )
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if session.monthly_filing.tax_office_id != user.tax_office_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    return session


@router.post("/sessions/{session_id}/messages", response_model=CollectMessageOut)
async def submit_message(
    session_id: str,
    payload: CollectMessageIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CollectMessageOut:
    session = await _load_session(db, session_id, user)

    return await _ingest_message(
        db=db,
        session=session,
        client=session.client,
        filing=session.monthly_filing,
        text=payload.text,
        channel=payload.channel,
        sender_name=payload.sender_name,
        received_date=payload.received_date,
    )


# ---------------------------------------------------------------------------
# 미리보기(dry-run) → 검토 → 확정 저장
#
# submit_message 는 파싱과 저장을 한 번에 처리한다. 대시보드의 "직접입력/파일
# 업로드"는 AI가 읽은 값을 사람이 확인한 뒤 반영해야 하므로, 같은 파이프라인을
# 파싱(_parse_and_match, DB 미접근) 과 저장(_persist_results) 으로 나눠 쓴다.
# ---------------------------------------------------------------------------


def _entry_key(employee_id: str | None, raw_name: str) -> str:
    return employee_id if employee_id else f"__name:{raw_name}"


async def _load_current_entries(
    db: AsyncSession, client: Client, filing: MonthlyFiling
) -> dict[str, PayrollEntry]:
    """이번 달에 이미 등록된 항목 — 직원 기준 lookup."""
    rows = list(
        (
            await db.execute(
                select(PayrollEntry).where(
                    PayrollEntry.monthly_filing_id == filing.id,
                    PayrollEntry.client_id == client.id,
                )
            )
        ).scalars().all()
    )
    return {_entry_key(r.employee_id, r.raw_name): r for r in rows}


def _preview_row(
    cand: PayrollEntryCandidate,
    employee_name: str | None,
    existing: PayrollEntry | None,
) -> ParsedEntryPreview:
    """AI가 읽은 후보 1건을 검토용 행으로 변환.

    AI는 "50만원 감액"처럼 증감만 말한 경우 금액을 음수로 돌려준다. 이번 달에 이미
    항목이 있으면 그 금액에 증감을 적용해 '수정'으로, 없으면 '신규'로 처리한다.
    """
    amount = cand.total_amount
    if existing is not None:
        amount = existing.total_amount + amount if amount < 0 else amount
    amount = max(0, amount)

    return ParsedEntryPreview(
        raw_name=cand.raw_name,
        employee_id=cand.employee_id,
        employee_name=employee_name,
        income_type=cand.income_type.value,
        total_amount=amount,
        non_taxable=max(0, cand.non_taxable),
        meal_amount=max(0, cand.meal_amount),
        car_amount=max(0, cand.car_amount),
        childcare_amount=max(0, cand.childcare_amount),
        match_status=cand.match_status.value,
        prev_amount=cand.prev_amount,
        # 기존 항목이 없는데 증감만 온 경우 금액을 확정할 수 없으므로 확인 대상으로 표시
        needs_followup=cand.needs_followup or (existing is None and cand.total_amount < 0),
        anomaly_notes=cand.anomaly_notes or None,
        mode="update" if existing is not None else "create",
        entry_id=existing.id if existing is not None else None,
        existing_amount=existing.total_amount if existing is not None else None,
    )


def _to_preview(
    session: CollectionSession,
    text: str,
    channel: str,
    matching: MatchingResult,
    employees: list[Employee],
    current_entries: dict[str, PayrollEntry],
    kind: str | None = None,
    attachments: list[dict] | None = None,
) -> CollectPreviewOut:
    emp_names = {e.id: e.name for e in employees}
    return CollectPreviewOut(
        session_id=session.id,
        source_text=text,
        channel=channel,
        kind=kind,
        attachments=attachments,
        entries=[
            _preview_row(
                c,
                emp_names.get(c.employee_id) if c.employee_id else None,
                current_entries.get(_entry_key(c.employee_id, c.raw_name)),
            )
            for c in matching.entries
        ],
        new_hire_suspected=len(matching.new_hire_followups),
        resignation_suspected=len(matching.resignation_followups),
        ambiguous=len(matching.ambiguous_followups),
        unconfirmed=len(matching.unconfirmed_followups),
    )


@router.post("/sessions/{session_id}/messages/preview", response_model=CollectPreviewOut)
async def preview_message(
    session_id: str,
    payload: CollectMessageIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CollectPreviewOut:
    """텍스트를 AI로 읽어 항목만 돌려준다. DB에는 아무것도 쓰지 않는다."""
    session = await _load_session(db, session_id, user)
    if not payload.text.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "내용이 비어 있습니다")

    client, filing = session.client, session.monthly_filing
    employees, prev_entries = await _build_context(db, client, filing)
    current_entries = await _load_current_entries(db, client, filing)
    matching = await _parse_and_match(payload.text, client, filing, employees, prev_entries)
    return _to_preview(
        session, payload.text, payload.channel, matching, employees, current_entries
    )


@router.post("/sessions/{session_id}/upload/preview", response_model=CollectPreviewOut)
async def preview_upload(
    session_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CollectPreviewOut:
    """급여파일(엑셀·CSV·이미지·PDF)을 AI로 읽어 항목만 돌려준다. DB 미저장."""
    session = await _load_session(db, session_id, user)

    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "빈 파일입니다")
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "25MB 초과 파일은 허용되지 않습니다"
        )

    intake = await intake_file(
        filename=file.filename or "upload",
        content=content,
        storage=get_storage(),
    )
    if not intake.text.strip() and not intake.images:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"파일에서 내용을 추출하지 못했습니다 ({intake.kind}). {intake.note or ''}",
        )

    client, filing = session.client, session.monthly_filing
    employees, prev_entries = await _build_context(db, client, filing)
    current_entries = await _load_current_entries(db, client, filing)
    matching = await _parse_and_match(
        intake.text, client, filing, employees, prev_entries, images=intake.images or None
    )
    attachments = (
        [{
            "filename": file.filename or "upload",
            "storage_key": intake.storage_key,
            "kind": intake.kind,
        }]
        if intake.storage_key
        else None
    )
    return _to_preview(
        session,
        intake.text,
        f"upload_{intake.kind}",
        matching,
        employees,
        current_entries,
        kind=intake.kind,
        attachments=attachments,
    )


@router.post("/sessions/{session_id}/messages/commit", response_model=CollectMessageOut)
async def commit_message(
    session_id: str,
    payload: CollectCommitIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CollectMessageOut:
    """미리보기에서 사람이 검토·수정한 항목을 저장한다. AI를 다시 호출하지 않는다."""
    session = await _load_session(db, session_id, user)
    if not payload.entries:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "반영할 항목이 없습니다")

    client, filing = session.client, session.monthly_filing
    employees, prev_entries = await _build_context(db, client, filing)
    valid_emp_ids = {e.id for e in employees}
    current_by_id = {
        e.id: e for e in (await _load_current_entries(db, client, filing)).values()
    }

    candidates: list[PayrollEntryCandidate] = []
    updates: list[tuple[PayrollEntry, PayrollEntryCandidate]] = []
    for item in payload.entries:
        try:
            income_type = IncomeType(item.income_type)
            match_status = MatchStatus(item.match_status)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"알 수 없는 구분값: {exc}") from exc
        employee_id = item.employee_id if item.employee_id in valid_emp_ids else None
        cand = PayrollEntryCandidate(
            raw_name=item.raw_name,
            employee_id=employee_id,
            income_type=income_type,
            total_amount=item.total_amount,
            non_taxable=item.non_taxable,
            meal_amount=item.meal_amount,
            car_amount=item.car_amount,
            childcare_amount=item.childcare_amount,
            match_status=match_status,
            prev_amount=item.prev_amount,
            anomaly_notes=item.anomaly_notes or {},
            needs_followup=item.needs_followup,
        )
        if item.mode == "update":
            target = current_by_id.get(item.entry_id) if item.entry_id else None
            if target is None:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"수정할 항목을 찾을 수 없습니다: {item.raw_name}",
                )
            updates.append((target, cand))
        else:
            candidates.append(cand)

    # 검토 후에도 확인이 필요한 항목(신규 의심·모호)은 세션이 '검토 필요'로 남도록
    # 후속 목록을 복원한다 — submit_message 경로와 상태 처리를 맞추기 위함.
    matching = MatchingResult(
        entries=candidates,
        new_hire_followups=[
            {"name": c.raw_name, "amount": c.total_amount}
            for c in candidates
            if c.match_status == MatchStatus.NEW_HIRE_SUSPECTED
        ],
        resignation_followups=[],
        ambiguous_followups=[
            {"name": c.raw_name}
            for c in candidates
            if c.match_status == MatchStatus.AMBIGUOUS
        ],
    )
    return await _persist_results(
        db,
        session,
        client,
        filing,
        matching,
        employees,
        payload.text,
        payload.channel,
        payload.attachments,
        sender_name=payload.sender_name,
        received_date=payload.received_date,
        prev_entries=prev_entries,
        updates=updates,
    )


# ---------------------------------------------------------------------------
# Pipeline internals
# ---------------------------------------------------------------------------


async def _build_context(
    db: AsyncSession,
    client: Client,
    filing: MonthlyFiling,
) -> tuple[list[Employee], list[PayrollEntry]]:
    """Load employee master and previous month payroll entries."""
    employees = list(
        (
            await db.execute(
                select(Employee)
                .where(Employee.client_id == client.id, Employee.status != EmploymentStatus.RESIGNED)
            )
        ).scalars().all()
    )

    prev_period = _prev_period(filing.period)
    prev_filing = (
        await db.execute(
            select(MonthlyFiling).where(
                MonthlyFiling.tax_office_id == filing.tax_office_id,
                MonthlyFiling.period == prev_period,
            )
        )
    ).scalar_one_or_none()

    prev_entries: list[PayrollEntry] = []
    if prev_filing:
        prev_entries = list(
            (
                await db.execute(
                    select(PayrollEntry).where(
                        PayrollEntry.monthly_filing_id == prev_filing.id,
                        PayrollEntry.client_id == client.id,
                    )
                )
            ).scalars().all()
        )

    return employees, prev_entries


async def _parse_and_match(
    text: str,
    client: Client,
    filing: MonthlyFiling,
    employees: list[Employee],
    prev_entries: list[PayrollEntry],
    images: list[tuple[bytes, str]] | None = None,
) -> MatchingResult:
    """Run AI parsing + matching engine. Pure logic, no DB writes."""
    # Build prev_amounts lookup (O(1) per employee instead of O(n))
    prev_by_emp = {p.employee_id: p.total_amount for p in prev_entries if p.employee_id}

    employee_master_payload = [
        {
            "id": e.id,
            "name": e.name,
            "last_amount": prev_by_emp.get(e.id),
        }
        for e in employees
    ]
    previous_month_payload = [
        {"name": p.raw_name, "employee_id": p.employee_id, "amount": p.total_amount}
        for p in prev_entries
        if p.employee_id
    ]

    parsed = await parse_payroll_message(
        raw_text=text,
        client_name=client.business_name,
        employee_master=employee_master_payload,
        previous_month_data=previous_month_payload,
        period=filing.period,
        images=images,
    )

    masters = [
        EmployeeMaster(
            id=e.id,
            name=e.name,
            last_amount=prev_by_emp.get(e.id),
            employee_code=e.employee_code,
        )
        for e in employees
    ]
    return reconcile(parsed, masters, prev_by_emp)


def _detect_field_anomalies(
    anomaly: dict,
    cand,
    prev: PayrollEntry,
    tax,
    si_np: int, si_hi: int, si_ei: int, si_ltc: int,
) -> None:
    """전월 대비 필드별 이상치를 anomaly_notes에 기록."""
    fields: dict[str, tuple[int, int]] = {}
    # 총액 변동은 기존 large_change로 이미 처리됨
    # 4대보험 변동 감지 (전월과 다르면 기록)
    if prev.national_pension > 0 and abs(si_np - prev.national_pension) > 1000:
        fields["national_pension"] = (prev.national_pension, si_np)
    if prev.health_insurance > 0 and abs(si_hi - prev.health_insurance) > 1000:
        fields["health_insurance"] = (prev.health_insurance, si_hi)
    # 소득세 변동 (20% 이상이면 기록)
    if prev.income_tax and prev.income_tax > 0:
        tax_change = abs(tax.income_tax - prev.income_tax) / prev.income_tax
        if tax_change > 0.2:
            fields["income_tax"] = (prev.income_tax, tax.income_tax)
    if fields:
        anomaly["field_changes"] = {
            k: {"prev": v[0], "curr": v[1]} for k, v in fields.items()
        }


def _computed_fields(
    cand: PayrollEntryCandidate,
    client: Client,
    defaults,
    matched_emp: Employee | None,
) -> tuple[dict, object, object]:
    """지급액에서 파생되는 금액 필드를 계산한다 (신규 생성·기존 수정 공용).

    반환: (PayrollEntry 필드 dict, 세액 계산 결과, 4대보험 계산 결과)
    """
    biz_code = (
        matched_emp.business_type_code
        if matched_emp and cand.income_type == IncomeType.BUSINESS
        else None
    )
    a_code = income_type_to_a_code(cand.income_type, is_corporation=client.is_corporation)

    # 비과세 지급항목 (plan.md 3.8):
    # 비과세는 상용근로(WAGE)에만 존재. 일용·사업·기타·퇴직소득은 비과세 0.
    # 1순위 — AI가 원시파일에서 추출한 값 (0 초과면 채택)
    # 2순위 — 거래처 세팅값 (없으면 시스템 비과세 한도)
    if cand.income_type == IncomeType.WAGE:
        meal = cand.meal_amount if cand.meal_amount > 0 else defaults.meal_default
        car = cand.car_amount if cand.car_amount > 0 else defaults.car_default
        childcare = cand.childcare_amount if cand.childcare_amount > 0 else defaults.childcare_default
        non_taxable = max(cand.non_taxable, meal + car + childcare)
        # 총지급액은 비과세를 이미 포함하므로, 비과세 합이 총지급액을 넘을 수 없음
        # (저액 급여자 음수 과세표준 방지). 초과 시 식대→자가운전→육아 순으로 축소.
        if non_taxable > cand.total_amount:
            non_taxable = cand.total_amount
            remaining = cand.total_amount
            meal = min(meal, remaining)
            remaining -= meal
            car = min(car, remaining)
            remaining -= car
            childcare = min(childcare, remaining)
    else:
        meal = car = childcare = 0
        non_taxable = 0

    taxable = cand.total_amount - non_taxable
    tax = calculate_withholding_tax(
        cand.income_type, taxable, dependents=1, business_type_code=biz_code,
    )
    # 4대보험 (plan.md 3.8): 거래처 세팅(요율 오버라이드 + apply 플래그)으로 계산.
    # TODO(ai_parser): AI가 원시파일에서 4대보험 금액을 추출하면 그 값을 1순위로 사용.
    si = defaults.social_insurance(taxable, cand.income_type)

    fields = {
        "a_code": a_code,
        "business_type_code": biz_code,
        "total_amount": cand.total_amount,
        "salary_amount": cand.total_amount if cand.income_type == IncomeType.WAGE else None,
        "bonus_amount": 0 if cand.income_type == IncomeType.WAGE else None,
        "non_taxable": non_taxable,
        "meal_amount": meal,
        "car_amount": car,
        "childcare_amount": childcare,
        "taxable": taxable,
        "national_pension": si.national_pension,
        "health_insurance": si.health_insurance,
        "employment_insurance": si.employment_insurance,
        "longterm_care": si.longterm_care,
        "income_tax": tax.income_tax,
        "local_tax": tax.local_tax,
    }
    return fields, tax, si


async def _persist_results(
    db: AsyncSession,
    session: CollectionSession,
    client: Client,
    filing: MonthlyFiling,
    matching: MatchingResult,
    employees: list[Employee],
    text: str,
    channel: str,
    attachments: list[dict] | None = None,
    sender_name: str | None = None,
    received_date: "date | None" = None,
    prev_entries: list[PayrollEntry] | None = None,
    updates: list[tuple[PayrollEntry, PayrollEntryCandidate]] | None = None,
) -> CollectMessageOut:
    """Save collection event and payroll entries to DB."""
    payload: dict = {
        "matched": len(matching.entries),
        "new_hire": len(matching.new_hire_followups),
        "resignation": len(matching.resignation_followups),
        "ambiguous": len(matching.ambiguous_followups),
    }
    if attachments:
        # 세무사 대시보드에서 AI 결과와 원본을 대조할 수 있도록 첨부 메타 보존
        payload["attachments"] = attachments

    # Record event — flush immediately to get ID for entry linking
    event = CollectionEvent(
        session_id=session.id,
        event_type=f"RECEIVE_{channel.upper()}",
        channel=channel,
        raw_text=text,
        raw_payload=payload,
        sender_name=sender_name,
        received_date=received_date,
    )
    db.add(event)
    await db.flush()

    # Deduplicate: skip if same filing + same employee already exists (across ALL sessions)
    # 같은 filing 내 다른 세션에서 이미 처리된 직원도 중복 방지
    existing_entries = list(
        (
            await db.execute(
                select(PayrollEntry).where(
                    PayrollEntry.monthly_filing_id == filing.id,
                    PayrollEntry.client_id == client.id,
                )
            )
        ).scalars().all()
    )
    existing_keys: set[str] = set()
    for ex in existing_entries:
        key = ex.employee_id if ex.employee_id else f"__name:{ex.raw_name}"
        existing_keys.add(key)

    emp_by_id = {e.id: e for e in employees}
    # 전월 엔트리 lookup (employee_id 기준) — 이상치 비교용. 비과세/4대보험 fallback으로는 사용 안 함.
    prev_by_emp: dict[str, PayrollEntry] = {}
    if prev_entries:
        for pe in prev_entries:
            if pe.employee_id:
                prev_by_emp[pe.employee_id] = pe
    needs_followup_count = 0

    # 거래처별 지급항목·4대보험 기본 세팅 (plan.md 3.8). 없으면 시스템 기본값.
    defaults = await load_payroll_defaults(db, client.id)

    for cand in matching.entries:
        dedup_key = cand.employee_id if cand.employee_id else f"__name:{cand.raw_name}"
        if dedup_key in existing_keys:
            continue

        matched_emp = emp_by_id.get(cand.employee_id) if cand.employee_id else None
        fields, tax, si = _computed_fields(cand, client, defaults, matched_emp)

        # 이상치 비교용 전월 엔트리
        prev = prev_by_emp.get(cand.employee_id) if cand.employee_id else None
        anomaly = dict(cand.anomaly_notes) if cand.anomaly_notes else {}
        if prev:
            _detect_field_anomalies(
                anomaly, cand, prev, tax,
                si.national_pension, si.health_insurance,
                si.employment_insurance, si.longterm_care,
            )

        entry = PayrollEntry(
            monthly_filing_id=filing.id,
            collection_session_id=session.id,
            collection_event_id=event.id,
            client_id=client.id,
            employee_id=cand.employee_id,
            raw_name=cand.raw_name,
            income_type=cand.income_type,
            match_status=cand.match_status,
            prev_amount=cand.prev_amount,
            anomaly_notes=anomaly or None,
            **fields,
        )
        if (
            cand.needs_followup
            and cand.match_status not in (MatchStatus.UNCONFIRMED, MatchStatus.NEW_HIRE_SUSPECTED)
        ):
            needs_followup_count += 1
        db.add(entry)

    # 기존 항목 수정 — "장수민 50만원 감액" 같은 요청은 새 항목이 아니라 갱신이다.
    # 금액이 바뀌므로 세액·4대보험을 다시 계산하고 승인 상태는 해제한다.
    updated_count = 0
    for entry, cand in updates or []:
        matched_emp = emp_by_id.get(cand.employee_id) if cand.employee_id else None
        fields, _tax, _si = _computed_fields(cand, client, defaults, matched_emp)
        for key, value in fields.items():
            setattr(entry, key, value)
        entry.raw_name = cand.raw_name
        entry.income_type = cand.income_type
        entry.collection_session_id = session.id
        entry.collection_event_id = event.id
        entry.approved = False
        updated_count += 1

    # Update session status
    session.status = (
        CollectionSessionStatus.NEEDS_REVIEW
        if (
            matching.new_hire_followups
            or matching.resignation_followups
            or matching.ambiguous_followups
            or needs_followup_count
        )
        else CollectionSessionStatus.RECEIVED
    )
    session.last_response_at = _dt.now(UTC)

    await db.commit()
    return CollectMessageOut(
        session_id=session.id,
        matched=sum(1 for c in matching.entries if c.match_status == MatchStatus.MATCHED),
        new_hire_suspected=len(matching.new_hire_followups),
        resignation_suspected=len(matching.resignation_followups),
        ambiguous=len(matching.ambiguous_followups),
        needs_followup=needs_followup_count,
        unconfirmed=len(matching.unconfirmed_followups),
        updated=updated_count,
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def _ingest_message(
    *,
    db: AsyncSession,
    session: CollectionSession,
    client: Client,
    filing: MonthlyFiling,
    text: str,
    channel: str,
    images: list[tuple[bytes, str]] | None = None,
    attachments: list[dict] | None = None,
    sender_name: str | None = None,
    received_date: "date | None" = None,
) -> CollectMessageOut:
    """
    attachments: 원본 파일 메타 [{"filename":..., "storage_key":..., "kind":..., "mime":...}]
                 세무사 대시보드에서 AI 결과와 대조하기 위해 저장.
    """
    # Safety net: 텍스트가 placeholder만 있고 이미지도 없으면 AI 환각 방지를 위해 스킵
    if not images and _is_only_placeholder(text):
        return await _record_unparseable(db, session, text, channel, attachments,
                                         sender_name=sender_name, received_date=received_date)

    employees, prev_entries = await _build_context(db, client, filing)
    matching = await _parse_and_match(text, client, filing, employees, prev_entries, images=images)
    return await _persist_results(
        db, session, client, filing, matching, employees, text, channel, attachments,
        sender_name=sender_name, received_date=received_date,
        prev_entries=prev_entries,
    )


_PLACEHOLDER_MARKERS = (
    "[이미지 업로드",
    "[이미지 첨부",
    "[첨부:",
)


def _is_only_placeholder(text: str) -> bool:
    """본문이 첨부 placeholder 라인만 있고 실제 텍스트가 없는지 확인."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return True
    return all(any(m in ln for m in _PLACEHOLDER_MARKERS) for ln in lines)


async def _record_unparseable(
    db: AsyncSession,
    session: CollectionSession,
    text: str,
    channel: str,
    attachments: list[dict] | None = None,
    sender_name: str | None = None,
    received_date: "date | None" = None,
) -> CollectMessageOut:
    """본문이 비어있거나 placeholder뿐일 때 — AI 호출 없이 세션만 검토 대기로 표시."""
    payload: dict = {"reason": "no parseable content"}
    if attachments:
        payload["attachments"] = attachments
    db.add(
        CollectionEvent(
            session_id=session.id,
            event_type=f"RECEIVE_{channel.upper()}_UNPARSEABLE",
            channel=channel,
            raw_text=text,
            raw_payload=payload,
            sender_name=sender_name,
            received_date=received_date,
        )
    )
    session.status = CollectionSessionStatus.NEEDS_REVIEW
    session.last_response_at = _dt.now(UTC)
    await db.commit()
    return CollectMessageOut(
        session_id=session.id,
        matched=0,
        new_hire_suspected=0,
        resignation_suspected=0,
        ambiguous=0,
        needs_followup=0,
    )


def _prev_period(period: str) -> str:
    y, m = int(period[:4]), int(period[5:7])
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


# Exposed so public router can reuse the pipeline
__all__ = ["_ingest_message", "router"]
