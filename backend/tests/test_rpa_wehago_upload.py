"""위하고 급여 업로드 RPA — 작업 등록 게이트, 에이전트 가져가기·결과 회신 (plan/16-wehago-rpa.md)."""

from __future__ import annotations

from collections import defaultdict

import pytest
from httpx import AsyncClient

CLAIM = "/api/v1/rpa/agent/claim"


async def _assign_wehago_codes(client_ids: list[str]) -> None:
    """사무소가 위하고 사원코드를 입력해 둔 상태 — 코드 없는 사원은 게이트 1에서 막힌다."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Employee

    async with SessionLocal() as db:
        employees = (
            await db.execute(select(Employee).where(Employee.client_id.in_(client_ids)))
        ).scalars().all()
        for n, emp in enumerate(employees, start=1):
            if not emp.employee_code:
                emp.employee_code = f"W{n:03d}"
        await db.commit()


async def _ready_clients(
    http: AsyncClient, auth_headers: dict, count: int
) -> tuple[str, list[str]]:
    """사업자번호가 있고 급여항목을 모두 승인한 거래처 count개와 그 신고 id."""
    clients = (await http.get("/api/v1/clients", headers=auth_headers)).json()
    with_number = {c["id"] for c in clients if c.get("business_number")}
    for filing in (await http.get("/api/v1/filings", headers=auth_headers)).json():
        entries = (
            await http.get(f"/api/v1/filings/{filing['id']}/entries", headers=auth_headers)
        ).json()
        by_client: dict[str, list[dict]] = defaultdict(list)
        for entry in entries:
            if entry["client_id"] in with_number:
                by_client[entry["client_id"]].append(entry)
        if len(by_client) < count:
            continue
        client_ids = list(by_client)[:count]
        for client_id in client_ids:
            for entry in by_client[client_id]:
                if not entry["approved"]:
                    r = await http.patch(
                        f"/api/v1/filings/{filing['id']}/entries/{entry['id']}",
                        json={"approved": True},
                        headers=auth_headers,
                    )
                    assert r.status_code == 200, r.text
        await _assign_wehago_codes(client_ids)
        return filing["id"], client_ids
    pytest.skip("시드에 사업자번호·급여항목이 있는 거래처가 부족하다")


async def _issue_agent(http: AsyncClient, auth_headers: dict, name: str) -> dict[str, str]:
    r = await http.post("/api/v1/rpa/agents", json={"name": name}, headers=auth_headers)
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    assert token.startswith("rpa_")
    return {"X-Agent-Token": token}


async def _enqueue(http: AsyncClient, auth_headers: dict, filing_id: str, client_ids: list[str]):
    return await http.post(
        "/api/v1/rpa/wehago-uploads",
        json={"filing_id": filing_id, "client_ids": client_ids},
        headers=auth_headers,
    )


@pytest.mark.asyncio
async def test_send_blocked_when_unautomated_income_type_present(
    http: AsyncClient, auth_headers: dict
):
    """일용소득처럼 자동화가 없는 소득유형이 섞여 있으면 거래처 전체가 전송 차단된다 (plan/16 §4-1).

    원천징수이행상황신고서가 소득유형을 전부 합산한 신고서 한 장이라, 일부 유형만
    위하고에 넣을 수 없다 — 자동화가 없는 유형에 데이터가 있으면 그 거래처는 통째로 막는다.
    (2026-09-30: 사업소득이, 2026-10-01: 기타소득이 자동화돼 §13-3-4·§13-3-3 이 테스트는
    여전히 자동화가 없는 일용소득으로 확인한다.)
    """
    filing_id, (client_id,) = await _ready_clients(http, auth_headers, 1)

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.payroll import IncomeType, PayrollEntry

    async with SessionLocal() as db:
        template = (
            await db.execute(
                select(PayrollEntry).where(
                    PayrollEntry.monthly_filing_id == filing_id,
                    PayrollEntry.client_id == client_id,
                )
            )
        ).scalars().first()
        other_entry = PayrollEntry(
            monthly_filing_id=template.monthly_filing_id,
            collection_session_id=template.collection_session_id,
            client_id=client_id,
            raw_name="일용소득자테스트",
            income_type=IncomeType.DAILY,
            total_amount=1_000_000,
            taxable=1_000_000,
            income_tax=30_000,
            local_tax=3_000,
            approved=True,
        )
        db.add(other_entry)
        await db.commit()
        entry_id = other_entry.id

    try:
        r = await _enqueue(http, auth_headers, filing_id, [client_id])
        assert r.status_code == 409, r.text
        assert "자동화" in r.json()["detail"]
        assert "일용소득" in r.json()["detail"]
    finally:
        # 다른 테스트가 같은 거래처를 재사용하므로(_ready_clients), 남겨두면 뒤 테스트가 전부 막힌다.
        async with SessionLocal() as db:
            await db.delete(await db.get(PayrollEntry, entry_id))
            await db.commit()


@pytest.mark.asyncio
async def test_preview_shows_income_type_breakdown(http: AsyncClient, auth_headers: dict):
    """전송 모달용 미리보기가 근로/사업/기타/일용 4칸을 항상 보여준다 (plan/16 §4-1)."""
    filing_id, (client_id,) = await _ready_clients(http, auth_headers, 1)

    r = await http.get(
        f"/api/v1/rpa/wehago-uploads/preview?filing_id={filing_id}", headers=auth_headers
    )
    assert r.status_code == 200, r.text
    row = next(p for p in r.json() if p["client_id"] == client_id)
    types = {t["income_type"]: t for t in row["income_types"]}
    assert set(types) == {"WAGE", "BUSINESS", "OTHER", "DAILY"}
    assert types["WAGE"]["count"] > 0
    assert types["WAGE"]["automated"] is True
    assert types["BUSINESS"]["count"] == 0
    assert types["BUSINESS"]["automated"] is True  # 2026-09-30 §13-3-4 — 사업소득도 자동화됨
    assert types["OTHER"]["automated"] is True  # 2026-10-01 §13-3-3 — 기타소득도 자동화됨
    assert types["DAILY"]["automated"] is False


@pytest.mark.asyncio
async def test_agent_claims_one_job_at_a_time_and_reports_result(
    http: AsyncClient, auth_headers: dict
):
    filing_id, (first_id, second_id) = await _ready_clients(http, auth_headers, 2)
    agent = await _issue_agent(http, auth_headers, "사무실 위하고 PC")
    other_agent = await _issue_agent(http, auth_headers, "다른 PC")

    r = await _enqueue(http, auth_headers, filing_id, [first_id])
    assert r.status_code == 201, r.text
    first_job = r.json()[0]
    assert first_job["status"] == "PENDING"
    assert first_job["business_number"]

    dup = await _enqueue(http, auth_headers, filing_id, [first_id])
    assert dup.status_code == 409, dup.text
    assert "진행 중" in dup.json()["detail"]

    r = await _enqueue(http, auth_headers, filing_id, [second_id])
    assert r.status_code == 201, r.text
    second_job = r.json()[0]

    claimed = (await http.post(CLAIM, headers=agent)).json()["job"]
    assert claimed["id"] == first_job["id"]
    assert claimed["status"] == "RUNNING"

    # 위하고 계정 하나로는 한 번에 한 건 — 다른 에이전트는 기다린다.
    assert (await http.post(CLAIM, headers=other_agent)).json()["job"] is None

    # 결과 회신 없이 다시 요청하면 재시작으로 보고 앞 작업을 실패 처리한 뒤 다음 작업을 준다.
    claimed = (await http.post(CLAIM, headers=agent)).json()["job"]
    assert claimed["id"] == second_job["id"]

    excel_url = f"/api/v1/rpa/agent/jobs/{second_job['id']}/payroll-excel"
    excel = await http.get(excel_url, headers=agent)
    assert excel.status_code == 200, excel.text
    assert excel.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml"
    )
    # 다른 에이전트는 남의 작업 파일을 받을 수 없다.
    assert (await http.get(excel_url, headers=other_agent)).status_code == 409

    done = await http.post(
        f"/api/v1/rpa/agent/jobs/{second_job['id']}/result",
        json={"status": "SUCCEEDED", "message": "위하고 업로드 완료"},
        headers=agent,
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "SUCCEEDED"

    jobs = {
        j["id"]: j
        for j in (
            await http.get(
                "/api/v1/rpa/jobs", params={"filing_id": filing_id}, headers=auth_headers
            )
        ).json()
    }
    assert jobs[first_job["id"]]["status"] == "FAILED"
    assert "재시작" in jobs[first_job["id"]]["result_message"]
    assert jobs[second_job["id"]]["status"] == "SUCCEEDED"


@pytest.mark.asyncio
async def test_upload_is_blocked_without_business_number_or_approval(
    http: AsyncClient, auth_headers: dict
):
    filing = (await http.get("/api/v1/filings", headers=auth_headers)).json()[0]
    created = await http.post(
        "/api/v1/clients", json={"business_name": "번호없는상사"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text

    r = await _enqueue(http, auth_headers, filing["id"], [created.json()["id"]])
    assert r.status_code == 409, r.text
    assert "사업자번호" in r.json()["detail"]

    clients = (await http.get("/api/v1/clients", headers=auth_headers)).json()
    with_number = {c["id"] for c in clients if c.get("business_number")}
    for f in (await http.get("/api/v1/filings", headers=auth_headers)).json():
        entries = (
            await http.get(f"/api/v1/filings/{f['id']}/entries", headers=auth_headers)
        ).json()
        for entry in entries:
            if not entry["approved"] and entry["client_id"] in with_number:
                r = await _enqueue(http, auth_headers, f["id"], [entry["client_id"]])
                assert r.status_code == 409, r.text
                assert "미승인" in r.json()["detail"]
                return
    pytest.skip("시드에 사업자번호가 있는 미승인 급여항목이 없다")


@pytest.mark.asyncio
async def test_pending_job_can_be_canceled_once(http: AsyncClient, auth_headers: dict):
    """한 거래처가 소득유형별로 여러 job을 받을 수 있으므로(§4-1) 전부 취소해야 다음
    테스트가 같은 거래처를 "이미 대기 중"으로 막히지 않고 재사용할 수 있다."""
    filing_id, (client_id,) = await _ready_clients(http, auth_headers, 1)
    r = await _enqueue(http, auth_headers, filing_id, [client_id])
    assert r.status_code == 201, r.text
    job_ids = [j["id"] for j in r.json()]

    for job_id in job_ids:
        canceled = await http.post(f"/api/v1/rpa/jobs/{job_id}/cancel", headers=auth_headers)
        assert canceled.status_code == 200, canceled.text
        assert canceled.json()["status"] == "CANCELED"

    again = await http.post(f"/api/v1/rpa/jobs/{job_ids[0]}/cancel", headers=auth_headers)
    assert again.status_code == 409, again.text


@pytest.mark.asyncio
async def test_missing_or_revoked_agent_token_is_rejected(http: AsyncClient, auth_headers: dict):
    assert (await http.post(CLAIM)).status_code == 401

    issued = await http.post(
        "/api/v1/rpa/agents", json={"name": "폐기될 PC"}, headers=auth_headers
    )
    assert issued.status_code == 201, issued.text
    headers = {"X-Agent-Token": issued.json()["token"]}
    assert (await http.post(CLAIM, headers=headers)).status_code == 200

    revoked = await http.delete(f"/api/v1/rpa/agents/{issued.json()['id']}", headers=auth_headers)
    assert revoked.status_code == 204, revoked.text
    assert (await http.post(CLAIM, headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_upload_is_blocked_when_employee_has_no_wehago_code(
    http: AsyncClient, auth_headers: dict
):
    """위하고는 사원코드로 사원을 연결한다 — 코드가 없으면 다른 사원에게 급여가 들어갈 수 있다."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Employee

    filing_id, (client_id,) = await _ready_clients(http, auth_headers, 1)
    async with SessionLocal() as db:
        emp = (
            await db.execute(select(Employee).where(Employee.client_id == client_id).limit(1))
        ).scalar_one()
        name, code = emp.name, emp.employee_code
        emp.employee_code = None
        await db.commit()
    try:
        r = await _enqueue(http, auth_headers, filing_id, [client_id])
        assert r.status_code == 409, r.text
        assert "사원코드" in r.json()["detail"] and name in r.json()["detail"]
    finally:
        async with SessionLocal() as db:
            (await db.get(Employee, emp.id)).employee_code = code
            await db.commit()


@pytest.mark.asyncio
async def test_preview_reason_names_the_income_type_missing_a_code(
    http: AsyncClient, auth_headers: dict
):
    """"위하고 사원코드 없는 사원 있음"만으로는 어느 소득유형인지 알 수 없다 — 괄호로 밝힌다."""
    filing_id, (client_id,) = await _ready_clients(http, auth_headers, 1)

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Employee
    from app.models.payroll import IncomeType, PayrollEntry

    async with SessionLocal() as db:
        template = (
            await db.execute(
                select(PayrollEntry).where(
                    PayrollEntry.monthly_filing_id == filing_id,
                    PayrollEntry.client_id == client_id,
                )
            )
        ).scalars().first()
        no_code_emp = Employee(client_id=client_id, name="사업소득코드누락", employee_code=None)
        db.add(no_code_emp)
        await db.flush()
        business_entry = PayrollEntry(
            monthly_filing_id=template.monthly_filing_id,
            collection_session_id=template.collection_session_id,
            client_id=client_id,
            employee_id=no_code_emp.id,
            raw_name=no_code_emp.name,
            income_type=IncomeType.BUSINESS,
            total_amount=1_000_000,
            taxable=1_000_000,
            approved=True,
        )
        db.add(business_entry)
        await db.commit()
        entry_id, emp_id = business_entry.id, no_code_emp.id

    try:
        r = await http.get(
            f"/api/v1/rpa/wehago-uploads/preview?filing_id={filing_id}", headers=auth_headers
        )
        assert r.status_code == 200, r.text
        row = next(p for p in r.json() if p["client_id"] == client_id)
        assert row["blocked_reason"] == "위하고 사원코드 없는 사원 있음 (사업소득)"
    finally:
        async with SessionLocal() as db:
            await db.delete(await db.get(PayrollEntry, entry_id))
            await db.delete(await db.get(Employee, emp_id))
            await db.commit()


async def _clear_payment_dates(filing_id: str, client_id: str) -> None:
    """실제 수집 경로처럼 급여 자료에 지급일이 없는 상태 (시드는 25일로 채워 둔다)."""
    from sqlalchemy import update

    from app.db import SessionLocal
    from app.models import PayrollEntry

    async with SessionLocal() as db:
        await db.execute(
            update(PayrollEntry)
            .where(PayrollEntry.monthly_filing_id == filing_id, PayrollEntry.client_id == client_id)
            .values(payment_date=None)
        )
        await db.commit()


@pytest.mark.asyncio
async def test_upload_needs_pay_date_and_claim_carries_it(http: AsyncClient, auth_headers: dict):
    """위하고 급여자료입력은 귀속연월·지급일로 조회한다 — 지급일을 못 정하면 전송을 막는다."""
    filing_id, (client_id,) = await _ready_clients(http, auth_headers, 1)
    period = next(
        f["period"]
        for f in (await http.get("/api/v1/filings", headers=auth_headers)).json()
        if f["id"] == filing_id
    )
    await _clear_payment_dates(filing_id, client_id)
    await http.post(f"/api/v1/clients/{client_id}/payroll-default/reset", headers=auth_headers)

    before = (
        await http.get(
            "/api/v1/rpa/wehago-uploads/preview", params={"filing_id": filing_id}, headers=auth_headers
        )
    ).json()
    assert next(r for r in before if r["client_id"] == client_id)["blocked_reason"] == "급여지급일 미설정"

    blocked = await _enqueue(http, auth_headers, filing_id, [client_id])
    assert blocked.status_code == 409, blocked.text
    assert "급여지급일 미설정" in blocked.json()["detail"]

    r = await http.put(
        f"/api/v1/clients/{client_id}/payroll-default",
        json={"pay_month_offset": 1, "pay_day": 31},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert (r.json()["pay_month_offset"], r.json()["pay_day"]) == (1, 31)

    preview = {
        row["client_id"]: row
        for row in (
            await http.get(
                "/api/v1/rpa/wehago-uploads/preview",
                params={"filing_id": filing_id},
                headers=auth_headers,
            )
        ).json()
    }
    from app.services.payroll_defaults import resolve_pay_date as _resolve

    assert preview[client_id]["blocked_reason"] is None
    assert preview[client_id]["pay_date"] == _resolve(period, 1, 31).isoformat()

    assert (await _enqueue(http, auth_headers, filing_id, [client_id])).status_code == 201
    after = (
        await http.get(
            "/api/v1/rpa/wehago-uploads/preview", params={"filing_id": filing_id}, headers=auth_headers
        )
    ).json()
    assert next(r for r in after if r["client_id"] == client_id)["blocked_reason"] == "이미 전송 대기·진행 중"
    agent = await _issue_agent(http, auth_headers, "지급일 확인 PC")
    claimed = (await http.post(CLAIM, headers=agent)).json()["job"]

    from app.services.payroll_defaults import resolve_pay_date

    assert claimed["pay_date"] == resolve_pay_date(period, 1, 31).isoformat()

    # 뒤따르는 테스트가 같은 거래처를 재사용하므로(_ready_clients) 남은 job을 전부 비운다
    # — 이 거래처가 WAGE 말고 다른 자동화 소득유형도 있으면 job이 여러 개일 수 있다.
    await http.post(
        f"/api/v1/rpa/agent/jobs/{claimed['id']}/result",
        json={"status": "SUCCEEDED", "message": "테스트 정리"}, headers=agent,
    )
    remaining = await http.post(CLAIM, headers=agent)
    while remaining.json()["job"] is not None:
        job = remaining.json()["job"]
        await http.post(
            f"/api/v1/rpa/agent/jobs/{job['id']}/result",
            json={"status": "SUCCEEDED", "message": "테스트 정리"}, headers=agent,
        )
        remaining = await http.post(CLAIM, headers=agent)


@pytest.mark.asyncio
async def test_wehago_uploads_creates_other_input_job_for_other_income(
    http: AsyncClient, auth_headers: dict
):
    """기타소득 자료가 있는 거래처는 WEHAGO_OTHER_INPUT 작업도 함께 생성된다 (2026-10-01, §13-3-3)."""
    filing_id, (client_id,) = await _ready_clients(http, auth_headers, 1)

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Employee
    from app.models.payroll import IncomeType, PayrollEntry

    async with SessionLocal() as db:
        template = (
            await db.execute(
                select(PayrollEntry).where(
                    PayrollEntry.monthly_filing_id == filing_id, PayrollEntry.client_id == client_id,
                )
            )
        ).scalars().first()
        other_emp = Employee(client_id=client_id, name="기타소득잡업테스트", employee_code="O099")
        db.add(other_emp)
        await db.flush()
        other_entry = PayrollEntry(
            monthly_filing_id=template.monthly_filing_id, collection_session_id=template.collection_session_id,
            client_id=client_id, employee_id=other_emp.id, raw_name=other_emp.name,
            income_type=IncomeType.OTHER, other_income_code="76",
            total_amount=1_000_000, taxable=1_000_000, income_tax=30_000, local_tax=3_000, approved=True,
        )
        db.add(other_entry)
        await db.commit()
        entry_id, emp_id = other_entry.id, other_emp.id

    try:
        r = await _enqueue(http, auth_headers, filing_id, [client_id])
        assert r.status_code == 201, r.text
        jobs = r.json()
        assert {j["kind"] for j in jobs} == {"WEHAGO_PAYROLL_INPUT", "WEHAGO_OTHER_INPUT"}

        # 뒤따르는 테스트가 같은 거래처를 재사용하므로(_ready_clients), PENDING으로 남기면
        # "이미 전송 대기 중"으로 막힌다 — 클레임·회신해서 비워둔다.
        agent = await _issue_agent(http, auth_headers, "정리용 PC")
        for _ in jobs:
            claimed = (await http.post(CLAIM, headers=agent)).json()["job"]
            await http.post(
                f"/api/v1/rpa/agent/jobs/{claimed['id']}/result",
                json={"status": "SUCCEEDED", "message": "테스트 정리"}, headers=agent,
            )
    finally:
        async with SessionLocal() as db:
            await db.delete(await db.get(PayrollEntry, entry_id))
            await db.delete(await db.get(Employee, emp_id))
            await db.commit()


@pytest.mark.asyncio
async def test_agent_other_income_excel_requires_valid_income_code(
    http: AsyncClient, auth_headers: dict
):
    """소득구분코드가 없으면 빈 엑셀을 올리는 대신 409로 막는다 (2026-10-01, §13-3-3)."""
    filing_id, (client_id,) = await _ready_clients(http, auth_headers, 1)

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Employee
    from app.models.payroll import IncomeType, PayrollEntry

    async with SessionLocal() as db:
        template = (
            await db.execute(
                select(PayrollEntry).where(
                    PayrollEntry.monthly_filing_id == filing_id, PayrollEntry.client_id == client_id,
                )
            )
        ).scalars().first()
        other_emp = Employee(client_id=client_id, name="코드없음테스트", employee_code="O098")
        db.add(other_emp)
        await db.flush()
        other_entry = PayrollEntry(
            monthly_filing_id=template.monthly_filing_id, collection_session_id=template.collection_session_id,
            client_id=client_id, employee_id=other_emp.id, raw_name=other_emp.name,
            income_type=IncomeType.OTHER, other_income_code=None,
            total_amount=1_000_000, taxable=1_000_000, approved=True,
        )
        db.add(other_entry)
        await db.commit()
        entry_id, emp_id = other_entry.id, other_emp.id

    try:
        r = await _enqueue(http, auth_headers, filing_id, [client_id])
        assert r.status_code == 201, r.text
        jobs = r.json()
        other_job = next(j for j in jobs if j["kind"] == "WEHAGO_OTHER_INPUT")

        agent = await _issue_agent(http, auth_headers, "기타소득 코드없음 PC")
        # claim 순서는 보장되지 않으므로 전부 가져와 OTHER kind 작업을 찾는다.
        for _ in jobs:
            claimed = (await http.post(CLAIM, headers=agent)).json()["job"]
            if claimed["id"] == other_job["id"]:
                excel = await http.get(
                    f"/api/v1/rpa/agent/jobs/{other_job['id']}/other-income-excel", headers=agent
                )
                assert excel.status_code == 409, excel.text
                assert "소득구분" in excel.json()["detail"]
            await http.post(
                f"/api/v1/rpa/agent/jobs/{claimed['id']}/result",
                json={"status": "FAILED", "message": "테스트 정리"}, headers=agent,
            )
    finally:
        async with SessionLocal() as db:
            await db.delete(await db.get(PayrollEntry, entry_id))
            await db.delete(await db.get(Employee, emp_id))
            await db.commit()
