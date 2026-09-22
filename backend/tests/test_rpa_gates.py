"""3게이트(전송·제작·발송 확정) — POST /productions, /filing-results/{id}/publish, 알림, 접수증 등록.

plan/16-wehago-rpa.md §4-2·§4-4·§4-5·§4-6·§7.
"""

from __future__ import annotations

from collections import defaultdict

import pytest
import pytest_asyncio
from httpx import AsyncClient

CLAIM = "/api/v1/rpa/agent/claim"


@pytest_asyncio.fixture(autouse=True)
async def _clean_rpa_state():
    """게이트 테스트마다 rpa_jobs·알림·신고결과 상태를 완전히 지운다.

    이 파일 테스트가 남긴 PENDING/RUNNING 작업이 test_rpa_wehago_upload.py 같은
    다른 RPA 테스트를 오염시키지 않도록.
    """
    from sqlalchemy import delete

    from app.db import SessionLocal
    from app.models import ClientFilingResult, RpaAgent, RpaJob, RpaNotification

    async def _wipe():
        async with SessionLocal() as db:
            await db.execute(delete(RpaNotification))
            await db.execute(delete(RpaJob))
            await db.execute(delete(RpaAgent))
            await db.execute(delete(ClientFilingResult))
            await db.commit()

    await _wipe()
    yield
    await _wipe()


async def _ready_clients(
    http: AsyncClient, auth_headers: dict, count: int
) -> tuple[str, list[str]]:
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
                    assert r.status_code == 200
        return filing["id"], client_ids
    pytest.skip("시드에 사업자번호·급여항목이 있는 거래처가 부족하다")


async def _issue_agent(http: AsyncClient, auth_headers: dict) -> dict[str, str]:
    r = await http.post("/api/v1/rpa/agents", json={"name": "PoC PC"}, headers=auth_headers)
    assert r.status_code == 201
    return {"X-Agent-Token": r.json()["token"]}


async def _complete_wehago_input(
    http: AsyncClient, auth_headers: dict, agent_headers: dict, filing_id: str, client_id: str
) -> str:
    """게이트 1 → 자동입력 성공 상태로 만든다. 반환: 완료된 job id."""
    r = await http.post(
        "/api/v1/rpa/wehago-uploads",
        json={"filing_id": filing_id, "client_ids": [client_id]},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    job_id = r.json()[0]["id"]

    claimed = (await http.post(CLAIM, headers=agent_headers)).json()["job"]
    assert claimed["id"] == job_id
    done = await http.post(
        f"/api/v1/rpa/agent/jobs/{job_id}/result",
        json={"status": "SUCCEEDED", "message": "위하고 자동입력 완료"},
        headers=agent_headers,
    )
    assert done.status_code == 200
    return job_id


# ---------------------------------------------------------------------------
# 게이트 2 — POST /productions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_production_requires_completed_auto_input(http: AsyncClient, auth_headers: dict):
    filing_id, (client_id,) = await _ready_clients(http, auth_headers, 1)

    # 자동입력 없이 곧바로 제작을 태우면 거부된다.
    r = await http.post(
        "/api/v1/rpa/productions",
        json={"filing_id": filing_id, "client_ids": [client_id]},
        headers=auth_headers,
    )
    assert r.status_code == 409, r.text
    assert "자동입력이 완료되지 않은" in r.json()["detail"]


@pytest.mark.asyncio
async def test_production_creates_monthly_production_job(http: AsyncClient, auth_headers: dict):
    filing_id, (client_id,) = await _ready_clients(http, auth_headers, 1)
    agent = await _issue_agent(http, auth_headers)
    await _complete_wehago_input(http, auth_headers, agent, filing_id, client_id)

    r = await http.post(
        "/api/v1/rpa/productions",
        json={"filing_id": filing_id, "client_ids": [client_id]},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    job = r.json()[0]
    assert job["kind"] == "MONTHLY_PRODUCTION"
    assert job["status"] == "PENDING"
    assert job["business_number"]

    # 같은 거래처를 다시 제작에 태우면 거부.
    dup = await http.post(
        "/api/v1/rpa/productions",
        json={"filing_id": filing_id, "client_ids": [client_id]},
        headers=auth_headers,
    )
    assert dup.status_code == 409, dup.text
    assert "제작이 대기·진행 중" in dup.json()["detail"]


# ---------------------------------------------------------------------------
# 알림 — 자동입력 완료 후 게이트 2 알림이 뜬다
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate2_notification_fired_on_wehago_input_success(
    http: AsyncClient, auth_headers: dict
):
    filing_id, (client_id,) = await _ready_clients(http, auth_headers, 1)
    agent = await _issue_agent(http, auth_headers)
    job_id = await _complete_wehago_input(http, auth_headers, agent, filing_id, client_id)

    r = await http.get("/api/v1/rpa/notifications?unread_only=true", headers=auth_headers)
    assert r.status_code == 200
    notes = r.json()
    gate2 = [n for n in notes if n["kind"] == "GATE2_REVIEW" and n["job_id"] == job_id]
    assert len(gate2) == 1, notes
    assert "제작" in gate2[0]["body"]

    read = await http.post(
        f"/api/v1/rpa/notifications/{gate2[0]['id']}/read", headers=auth_headers
    )
    assert read.status_code == 200
    assert read.json()["read_at"] is not None


@pytest.mark.asyncio
async def test_failure_notification_fired(http: AsyncClient, auth_headers: dict):
    filing_id, (client_id,) = await _ready_clients(http, auth_headers, 1)
    agent = await _issue_agent(http, auth_headers)

    r = await http.post(
        "/api/v1/rpa/wehago-uploads",
        json={"filing_id": filing_id, "client_ids": [client_id]},
        headers=auth_headers,
    )
    job_id = r.json()[0]["id"]
    await http.post(CLAIM, headers=agent)
    await http.post(
        f"/api/v1/rpa/agent/jobs/{job_id}/result",
        json={"status": "FAILED", "message": "위하고 로그인 실패"},
        headers=agent,
    )

    notes = (
        await http.get("/api/v1/rpa/notifications", headers=auth_headers)
    ).json()
    failures = [n for n in notes if n["kind"] == "FAILURE" and n["job_id"] == job_id]
    assert len(failures) == 1
    assert "로그인 실패" in failures[0]["body"]


# ---------------------------------------------------------------------------
# 게이트 3 — POST /filing-results/{id}/publish + 에이전트 접수증 등록
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_requires_filing_result_and_stays_private_until_confirmed(
    http: AsyncClient, auth_headers: dict
):
    filing_id, (client_id,) = await _ready_clients(http, auth_headers, 1)
    agent = await _issue_agent(http, auth_headers)
    await _complete_wehago_input(http, auth_headers, agent, filing_id, client_id)

    # 제작 작업 등록 및 에이전트가 가져가기
    r = await http.post(
        "/api/v1/rpa/productions",
        json={"filing_id": filing_id, "client_ids": [client_id]},
        headers=auth_headers,
    )
    prod_job_id = r.json()[0]["id"]
    claimed = (await http.post(CLAIM, headers=agent)).json()["job"]
    assert claimed["id"] == prod_job_id

    # 에이전트가 접수증·납부서 등록 (published_at은 아직 NULL이어야 함)
    filing_res = await http.post(
        f"/api/v1/rpa/agent/jobs/{prod_job_id}/filing-result",
        json={
            "client_id": client_id,
            "period": claimed["period"],
            "settled_tax": 340000,
            "epayment_number": "12345678901234567",
            "due_date": "2026-09-10",
            "receipt_key": "s3://receipts/abc.pdf",
            "receipt_name": "홈택스_접수증_2026-08.pdf",
        },
        headers=agent,
    )
    assert filing_res.status_code == 200, filing_res.text
    body = filing_res.json()
    filing_result_id = body["id"]
    assert body["published_at"] is None
    assert body["settled_tax"] == 340000
    assert body["source"] == "RPA"

    # 제작 작업을 SUCCEEDED로 마무리 → 게이트 3 알림 발송
    await http.post(
        f"/api/v1/rpa/agent/jobs/{prod_job_id}/result",
        json={"status": "SUCCEEDED", "message": "홈택스·위택스 접수증 회수 완료"},
        headers=agent,
    )
    notes = (
        await http.get("/api/v1/rpa/notifications?unread_only=true", headers=auth_headers)
    ).json()
    gate3 = [n for n in notes if n["kind"] == "GATE3_PUBLISH" and n["job_id"] == prod_job_id]
    assert len(gate3) == 1
    assert "발송 확정" in gate3[0]["body"]

    # 게이트 3 클릭 — published_at·confirmed_by_user_id 채워짐
    pub = await http.post(
        f"/api/v1/rpa/filing-results/{filing_result_id}/publish", headers=auth_headers
    )
    assert pub.status_code == 200, pub.text
    published = pub.json()
    assert published["published_at"] is not None
    assert published["confirmed_by_user_id"]

    # 두 번 확정하면 거부.
    again = await http.post(
        f"/api/v1/rpa/filing-results/{filing_result_id}/publish", headers=auth_headers
    )
    assert again.status_code == 409
    assert "이미 발송 확정" in again.json()["detail"]


@pytest.mark.asyncio
async def test_agent_filing_result_rejects_mismatched_client(
    http: AsyncClient, auth_headers: dict
):
    filing_id, (client_id, other_id) = await _ready_clients(http, auth_headers, 2)
    agent = await _issue_agent(http, auth_headers)
    await _complete_wehago_input(http, auth_headers, agent, filing_id, client_id)

    r = await http.post(
        "/api/v1/rpa/productions",
        json={"filing_id": filing_id, "client_ids": [client_id]},
        headers=auth_headers,
    )
    prod_job_id = r.json()[0]["id"]
    (await http.post(CLAIM, headers=agent)).json()

    bad = await http.post(
        f"/api/v1/rpa/agent/jobs/{prod_job_id}/filing-result",
        json={"client_id": other_id, "period": "2026-08", "settled_tax": 1000},
        headers=agent,
    )
    assert bad.status_code == 400
    assert "일치하지 않습니다" in bad.json()["detail"]


# ---------------------------------------------------------------------------
# 하단 작업바 — [확인] 처리 (plan/17-certificate-issuance.md §4-9)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acknowledge_hides_finished_job_from_bar(http: AsyncClient, auth_headers: dict):
    filing_id, (client_id,) = await _ready_clients(http, auth_headers, 1)
    agent = await _issue_agent(http, auth_headers)

    r = await http.post(
        "/api/v1/rpa/wehago-uploads",
        json={"filing_id": filing_id, "client_ids": [client_id]},
        headers=auth_headers,
    )
    job_id = r.json()[0]["id"]
    bar = "/api/v1/rpa/jobs?unacknowledged=true"

    # 진행 중에는 바에 있고, 확인 처리할 수 없다
    assert job_id in [j["id"] for j in (await http.get(bar, headers=auth_headers)).json()]
    r = await http.post(f"/api/v1/rpa/jobs/{job_id}/acknowledge", headers=auth_headers)
    assert r.status_code == 409

    await http.post(CLAIM, headers=agent)
    await http.post(
        f"/api/v1/rpa/agent/jobs/{job_id}/result",
        json={"status": "SUCCEEDED", "message": "완료"},
        headers=agent,
    )

    r = await http.post(f"/api/v1/rpa/jobs/{job_id}/acknowledge", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["acknowledged_at"] is not None

    # 바에서는 사라지고 전체 내역에는 남는다
    assert job_id not in [j["id"] for j in (await http.get(bar, headers=auth_headers)).json()]
    assert job_id in [
        j["id"] for j in (await http.get("/api/v1/rpa/jobs", headers=auth_headers)).json()
    ]
