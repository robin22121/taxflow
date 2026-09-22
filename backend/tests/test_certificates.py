"""증명원 발급 메뉴 — 요청 → 에이전트 발급 → 폴더 확인 → 고객 발송 → 30일 만료 (plan/17 §4-9)."""

from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient

BASE = "/api/v1/certificates"


@pytest_asyncio.fixture(autouse=True)
async def _clean_state():
    from sqlalchemy import delete

    from app.db import SessionLocal
    from app.models import CertificateIssue, RpaAgent, RpaJob, RpaNotification

    async def _wipe():
        async with SessionLocal() as db:
            await db.execute(delete(CertificateIssue))
            await db.execute(delete(RpaNotification))
            await db.execute(delete(RpaJob))
            await db.execute(delete(RpaAgent))
            await db.commit()

    await _wipe()
    yield
    await _wipe()


async def _client_id(http: AsyncClient, auth_headers: dict) -> str:
    clients = (await http.get("/api/v1/clients", headers=auth_headers)).json()
    return clients[0]["id"]


async def _agent(http: AsyncClient, auth_headers: dict) -> dict[str, str]:
    r = await http.post("/api/v1/rpa/agents", json={"name": "증명발급 PC"}, headers=auth_headers)
    assert r.status_code == 201
    return {"X-Agent-Token": r.json()["token"]}


async def _issued_job(http: AsyncClient, auth_headers: dict) -> tuple[str, str, dict]:
    """발급 요청 → 에이전트 발급·업로드·종료까지. 반환: (job_id, issue_id, agent_headers)."""
    client_id = await _client_id(http, auth_headers)
    r = await http.post(
        f"{BASE}/issue-requests",
        json={"client_id": client_id, "cert_types": ["BUSINESS_REGISTRATION"]},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["job"]["id"]

    agent = await _agent(http, auth_headers)
    claimed = (await http.post(f"{BASE}/agent/claim", headers=agent)).json()
    assert claimed["job"]["id"] == job_id
    issue_id = claimed["issues"][0]["id"]

    r = await http.post(
        f"{BASE}/agent/issues/{issue_id}/file",
        files={"file": ("사업자등록증명.pdf", b"%PDF-1.4 test", "application/pdf")},
        data={"local_path": r"D:\이지원천\증명원\상도기업\20260922_사업자등록증명.pdf"},
        headers=agent,
    )
    assert r.status_code == 200, r.text
    r = await http.post(f"{BASE}/agent/jobs/{job_id}/finish", json={"status": "SUCCEEDED"}, headers=agent)
    assert r.json()["status"] == "SUCCEEDED"
    return job_id, issue_id, agent


@pytest.mark.asyncio
async def test_catalog_and_unavailable_rejected(http: AsyncClient, auth_headers: dict):
    catalog = (await http.get(f"{BASE}/catalog", headers=auth_headers)).json()
    assert {c["category"] for c in catalog} == {"HOMETAX", "WETAX", "EMPLOYEE"}
    hometax = [c for c in catalog if c["category"] == "HOMETAX"]
    assert all(c["available"] for c in hometax)
    assert {c["code"] for c in catalog if c["period"]} == {"TAX_PAYMENT_HISTORY", "INCOME_AMOUNT", "VAT_BASE"}

    r = await http.post(
        f"{BASE}/issue-requests",
        json={"client_id": await _client_id(http, auth_headers), "cert_types": ["WITHHOLDING_RECEIPT"]},
        headers=auth_headers,
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_period_years_only_on_period_certificates(http: AsyncClient, auth_headers: dict):
    r = await http.post(
        f"{BASE}/issue-requests",
        json={
            "client_id": await _client_id(http, auth_headers),
            "cert_types": ["INCOME_AMOUNT", "BUSINESS_REGISTRATION"],
            "period_years": 3,
        },
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    options = {i["cert_type"]: i["options"] for i in r.json()["issues"]}
    assert options["INCOME_AMOUNT"]["period_years"] == 3
    assert "period_years" not in options["BUSINESS_REGISTRATION"]

    bad = await http.post(
        f"{BASE}/issue-requests",
        json={"client_id": await _client_id(http, auth_headers), "cert_types": ["VAT_BASE"], "period_years": 2},
        headers=auth_headers,
    )
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_wehago_agent_does_not_take_certificate_jobs(http: AsyncClient, auth_headers: dict):
    await http.post(
        f"{BASE}/issue-requests",
        json={"client_id": await _client_id(http, auth_headers), "cert_types": ["TAX_CLEARANCE_ETC"]},
        headers=auth_headers,
    )
    agent = await _agent(http, auth_headers)
    assert (await http.post("/api/v1/rpa/agent/claim", headers=agent)).json()["job"] is None
    assert (await http.post(f"{BASE}/agent/claim", headers=agent)).json()["job"] is not None


@pytest.mark.asyncio
async def test_issue_open_folder_then_deliver(http: AsyncClient, auth_headers: dict):
    job_id, issue_id, agent = await _issued_job(http, auth_headers)

    detail = (await http.get(f"{BASE}/jobs/{job_id}", headers=auth_headers)).json()
    issue = detail["issues"][0]
    assert issue["status"] == "ISSUED" and issue["has_file"] and issue["local_path"].endswith(".pdf")
    assert detail["job"]["step_progress"]["BUSINESS_REGISTRATION"] == "done"

    # 폴더 확인 전에는 발송 불가
    r = await http.post(f"{BASE}/jobs/{job_id}/deliver", json={"channel": "sms", "phone": "010-1234-5678"}, headers=auth_headers)
    assert r.status_code == 409

    await http.post(f"{BASE}/jobs/{job_id}/open-folder", headers=auth_headers)
    requests = (await http.get(f"{BASE}/agent/folder-requests", headers=agent)).json()
    assert [i["id"] for i in requests] == [issue_id]
    await http.post(f"{BASE}/agent/issues/{issue_id}/folder-opened", headers=agent)
    assert (await http.get(f"{BASE}/agent/folder-requests", headers=agent)).json() == []

    r = await http.post(f"{BASE}/jobs/{job_id}/deliver", json={"channel": "alimtalk", "phone": "010-1234-5678"}, headers=auth_headers)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["accepted"] and "30일간 유효" in out["body"]

    # 안내문의 공개 링크로 고객이 받을 수 있다
    token_url = next(line.strip() for line in out["body"].splitlines() if "/public/certificates/" in line)
    path = token_url[token_url.index("/api/v1/public/"):]
    r = await http.get(path)
    assert r.status_code == 200 and r.content == b"%PDF-1.4 test"

    job = (await http.get(f"{BASE}/jobs/{job_id}", headers=auth_headers)).json()["job"]
    assert job["step_progress"]["delivered"] == "done"


@pytest.mark.asyncio
async def test_deliver_email_attaches_pdf(http: AsyncClient, auth_headers: dict, monkeypatch):
    from app.api import certificates as api
    from app.channels.base import SendResult

    sent: list[dict] = []

    class Capture:
        async def send(self, recipient, *, body, template_code=None, attachments=None, **_):
            sent.append({"to": recipient.email, "subject": template_code, "body": body, "attachments": attachments})
            return SendResult(channel="email_test", accepted=True, provider_msg_id="x")

    monkeypatch.setattr(api, "get_email_channel", lambda: Capture())
    job_id, _, _ = await _issued_job(http, auth_headers)
    await http.post(f"{BASE}/jobs/{job_id}/open-folder", headers=auth_headers)

    bad = await http.post(f"{BASE}/jobs/{job_id}/deliver", json={"channel": "email", "email": "없음"}, headers=auth_headers)
    assert bad.status_code == 422

    r = await http.post(
        f"{BASE}/jobs/{job_id}/deliver", json={"channel": "email", "email": "owner@example.com"}, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["to"] == "owner@example.com"
    mail = sent[0]
    assert mail["to"] == "owner@example.com" and "증명원 발급 안내" in mail["subject"]
    assert "30일간 유효" in mail["body"]
    assert [(name, data) for name, data in mail["attachments"]] == [("사업자등록증명.pdf", b"%PDF-1.4 test")]


@pytest.mark.asyncio
async def test_server_copy_deleted_after_30_days(http: AsyncClient, auth_headers: dict):
    from app.db import SessionLocal
    from app.models import CertificateIssue

    job_id, issue_id, _ = await _issued_job(http, auth_headers)
    async with SessionLocal() as db:
        issue = await db.get(CertificateIssue, issue_id)
        issue.expires_at = issue.expires_at - timedelta(days=31)
        await db.commit()

    r = await http.get(f"{BASE}/issues/{issue_id}/file", headers=auth_headers)
    assert r.status_code == 410
    detail = (await http.get(f"{BASE}/jobs/{job_id}", headers=auth_headers)).json()
    assert detail["issues"][0]["has_file"] is False
    # 원본 경로 기록은 남는다
    assert detail["issues"][0]["local_path"]


# ---------------------------------------------------------------------------
# 직원용 증명서 — 서버 생성 (재직·경력)
# ---------------------------------------------------------------------------


async def _employees(http: AsyncClient, auth_headers: dict) -> tuple[str, list[dict]]:
    for client in (await http.get("/api/v1/clients", headers=auth_headers)).json():
        emps = (await http.get(f"/api/v1/clients/{client['id']}/employees", headers=auth_headers)).json()
        if any(e["hired_at"] and not e["resigned_at"] for e in emps):
            return client["id"], emps
    pytest.skip("시드에 입사일 있는 재직 직원이 없다")


@pytest.mark.asyncio
async def test_employee_certificates_generated_immediately(http: AsyncClient, auth_headers: dict):
    client_id, emps = await _employees(http, auth_headers)
    active = next(e for e in emps if e["hired_at"] and not e["resigned_at"])

    r = await http.post(
        f"{BASE}/issue-requests",
        json={"client_id": client_id, "cert_types": ["EMPLOYMENT_CERT", "CAREER_CERT"],
              "employee_ids": [active["id"]], "purpose": "금융기관 제출용"},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["job"]["status"] == "SUCCEEDED"
    assert [i["status"] for i in body["issues"]] == ["ISSUED", "ISSUED"]
    assert all(active["name"] in i["title"] and i["employee_id"] == active["id"] for i in body["issues"])

    pdf = await http.get(f"{BASE}/issues/{body['issues'][0]['id']}/file", headers=auth_headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    # [폴더 열어 확인] → 에이전트가 서버 사본을 내려받아 저장 경로를 보고
    agent = await _agent(http, auth_headers)
    await http.post(f"{BASE}/jobs/{body['job']['id']}/open-folder", headers=auth_headers)
    pending = (await http.get(f"{BASE}/agent/folder-requests", headers=agent)).json()
    assert {i["id"] for i in pending} == {i["id"] for i in body["issues"]}
    issue_id = pending[0]["id"]
    got = await http.get(f"{BASE}/agent/issues/{issue_id}/file", headers=agent)
    assert got.content.startswith(b"%PDF")
    r = await http.post(
        f"{BASE}/agent/issues/{issue_id}/folder-opened",
        json={"local_path": "D:/이지원천/증명원/x.pdf"}, headers=agent,
    )
    assert r.json()["local_path"] == "D:/이지원천/증명원/x.pdf"


@pytest.mark.asyncio
async def test_employee_certificate_rules(http: AsyncClient, auth_headers: dict):
    from app.db import SessionLocal
    from app.models import Employee

    client_id, emps = await _employees(http, auth_headers)
    target = next(e for e in emps if e["hired_at"] and not e["resigned_at"])

    # 홈택스 증명원과 섞으면 거부, 직원 미선택도 거부
    mixed = await http.post(
        f"{BASE}/issue-requests",
        json={"client_id": client_id, "cert_types": ["CAREER_CERT", "BUSINESS_REGISTRATION"], "employee_ids": [target["id"]]},
        headers=auth_headers,
    )
    assert mixed.status_code == 422
    none = await http.post(
        f"{BASE}/issue-requests", json={"client_id": client_id, "cert_types": ["CAREER_CERT"]}, headers=auth_headers
    )
    assert none.status_code == 422

    # 퇴사자는 재직증명서 실패(사유), 경력증명서는 발급
    from datetime import date

    async with SessionLocal() as db:
        emp = await db.get(Employee, target["id"])
        original = emp.resigned_at
        emp.resigned_at = date(2026, 6, 30)
        await db.commit()
    try:
        r = await http.post(
            f"{BASE}/issue-requests",
            json={"client_id": client_id, "cert_types": ["EMPLOYMENT_CERT", "CAREER_CERT"], "employee_ids": [target["id"]]},
            headers=auth_headers,
        )
        issues = {i["cert_type"]: i for i in r.json()["issues"]}
        assert issues["EMPLOYMENT_CERT"]["status"] == "FAILED" and "경력증명서" in issues["EMPLOYMENT_CERT"]["failure_reason"]
        assert issues["CAREER_CERT"]["status"] == "ISSUED"
        assert r.json()["job"]["status"] == "FAILED"
    finally:
        async with SessionLocal() as db:
            emp = await db.get(Employee, target["id"])
            emp.resigned_at = original
            await db.commit()
