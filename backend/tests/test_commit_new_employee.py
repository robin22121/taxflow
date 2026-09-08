"""검토 화면에서 신규 입사자를 주민번호와 함께 커밋하면 직원 마스터가 생긴다."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _pick_session(http: AsyncClient, auth_headers: dict) -> tuple[str, str]:
    filings = (await http.get("/api/v1/filings", headers=auth_headers)).json()
    apr = next(f for f in filings if f["period"] == "2026-04")
    dash = (await http.get(f"/api/v1/filings/{apr['id']}/dashboard", headers=auth_headers)).json()
    return apr["id"], dash["sessions"][0]["id"]


def _entry(name: str, new_employee: dict | None) -> dict:
    return {
        "raw_name": name,
        "income_type": "WAGE",
        "total_amount": 3_000_000,
        "match_status": "NEW_HIRE_SUSPECTED",
        "new_employee": new_employee,
    }


@pytest.mark.asyncio
async def test_commit_creates_employee_with_rrn(http: AsyncClient, auth_headers: dict):
    filing_id, session_id = await _pick_session(http, auth_headers)
    res = await http.post(
        f"/api/v1/collect/sessions/{session_id}/messages/commit",
        headers=auth_headers,
        json={
            "text": "신규 박신입 300만원",
            "channel": "manual",
            "sender_name": "직접입력",
            "received_date": "2026-04-10",
            "entries": [
                _entry("박신입", {"rrn": "900101-1234567", "hired_at": "2026-04-01"})
            ],
        },
    )
    assert res.status_code == 200, res.text

    # 직원 마스터에 등록되고, 표시용 뒤 4자리가 실제 마지막 4자리여야 한다.
    dash = (await http.get(f"/api/v1/filings/{filing_id}/dashboard", headers=auth_headers)).json()
    client_id = dash["sessions"][0]["client_id"]
    employees = (
        await http.get(f"/api/v1/clients/{client_id}/employees", headers=auth_headers)
    ).json()
    created = next(e for e in employees if e["name"] == "박신입")
    assert created["rrn_last4"] == "4567"
    assert created["status"] == "ACTIVE"
    assert created["hired_at"] == "2026-04-01"


@pytest.mark.asyncio
async def test_commit_rejects_malformed_rrn(http: AsyncClient, auth_headers: dict):
    _, session_id = await _pick_session(http, auth_headers)
    res = await http.post(
        f"/api/v1/collect/sessions/{session_id}/messages/commit",
        headers=auth_headers,
        json={
            "text": "신규 오타김 300만원",
            "channel": "manual",
            "sender_name": "직접입력",
            "received_date": "2026-04-10",
            "entries": [_entry("오타김", {"rrn": "9001011"})],
        },
    )
    assert res.status_code == 400, res.text
    assert "주민등록번호" in res.json()["detail"]


@pytest.mark.asyncio
async def test_commit_without_rrn_registers_pending(http: AsyncClient, auth_headers: dict):
    filing_id, session_id = await _pick_session(http, auth_headers)
    res = await http.post(
        f"/api/v1/collect/sessions/{session_id}/messages/commit",
        headers=auth_headers,
        json={
            "text": "신규 나중에 250만원",
            "channel": "manual",
            "sender_name": "직접입력",
            "received_date": "2026-04-10",
            "entries": [_entry("나중에", {"hired_at": "2026-04-05"})],
        },
    )
    assert res.status_code == 200, res.text

    dash = (await http.get(f"/api/v1/filings/{filing_id}/dashboard", headers=auth_headers)).json()
    client_id = dash["sessions"][0]["client_id"]
    employees = (
        await http.get(f"/api/v1/clients/{client_id}/employees", headers=auth_headers)
    ).json()
    created = next(e for e in employees if e["name"] == "나중에")
    assert created["rrn_last4"] is None
    assert created["status"] == "PENDING"
