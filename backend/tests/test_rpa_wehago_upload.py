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
    filing_id, (client_id,) = await _ready_clients(http, auth_headers, 1)
    r = await _enqueue(http, auth_headers, filing_id, [client_id])
    assert r.status_code == 201, r.text
    job_id = r.json()[0]["id"]

    canceled = await http.post(f"/api/v1/rpa/jobs/{job_id}/cancel", headers=auth_headers)
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["status"] == "CANCELED"

    again = await http.post(f"/api/v1/rpa/jobs/{job_id}/cancel", headers=auth_headers)
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

    assert (await _enqueue(http, auth_headers, filing_id, [client_id])).status_code == 201
    agent = await _issue_agent(http, auth_headers, "지급일 확인 PC")
    claimed = (await http.post(CLAIM, headers=agent)).json()["job"]

    from app.services.payroll_defaults import resolve_pay_date

    assert claimed["pay_date"] == resolve_pay_date(period, 1, 31).isoformat()
