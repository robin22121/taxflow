"""입·퇴사 등록 — 사업주 통보 → 세무사 승인 (plan/12-owner-portal.md §5.2).

검증 목표
1. 승인 전에는 직원 마스터가 바뀌지 않는다
2. 승인해야 Employee가 생기거나 퇴사 처리된다
3. 주민번호는 이 경로로 들어올 수 없다 (구조적 차단)
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _portal_token(http: AsyncClient, auth_headers: dict, client_id: str) -> str:
    r = await http.get(f"/api/v1/clients/{client_id}/portal-link", headers=auth_headers)
    return r.json()["url"].rsplit("/", 1)[-1]


async def _client_id(http: AsyncClient, auth_headers: dict, index: int) -> str:
    clients = (await http.get("/api/v1/clients", headers=auth_headers)).json()
    return clients[index]["id"]


async def _employee_names(http: AsyncClient, auth_headers: dict, client_id: str) -> list[str]:
    rows = (await http.get(f"/api/v1/clients/{client_id}/employees", headers=auth_headers)).json()
    return [e["name"] for e in rows]


def test_change_request_model_has_no_rrn_column():
    """§4.7 G4 — 이 경로에는 주민번호를 담을 곳이 아예 없다."""
    from app.models import EmployeeChangeRequest

    columns = set(EmployeeChangeRequest.__table__.columns.keys())
    assert not any("rrn" in c for c in columns)
    assert not any("resident" in c for c in columns)


@pytest.mark.asyncio
async def test_hire_needs_approval_before_master_changes(http: AsyncClient, auth_headers: dict):
    client_id = await _client_id(http, auth_headers, 0)
    token = await _portal_token(http, auth_headers, client_id)

    created = await http.post(
        f"/api/v1/public/r/{token}/employee-change",
        json={"change_type": "HIRE", "name": "신입사원", "hired_at": "2026-04-01"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "PENDING"
    request_id = created.json()["id"]

    # 승인 전 — 마스터는 그대로다.
    assert "신입사원" not in await _employee_names(http, auth_headers, client_id)

    pending = (await http.get("/api/v1/employee-changes", headers=auth_headers)).json()
    assert any(row["id"] == request_id for row in pending)

    approved = await http.post(
        f"/api/v1/employee-changes/{request_id}/approve", headers=auth_headers
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert "신입사원" in await _employee_names(http, auth_headers, client_id)


@pytest.mark.asyncio
async def test_resign_marks_employee_and_drops_from_portal_list(
    http: AsyncClient, auth_headers: dict
):
    """퇴사 승인 후에는 포털 명단(재직자)에서 빠진다."""
    client_id = await _client_id(http, auth_headers, 1)
    token = await _portal_token(http, auth_headers, client_id)

    roster = (await http.get(f"/api/v1/public/r/{token}/employees")).json()
    assert len(roster) > 0
    target = roster[0]

    created = await http.post(
        f"/api/v1/public/r/{token}/employee-change",
        json={
            "change_type": "RESIGN",
            "employee_id": target["id"],
            "resigned_at": "2026-04-20",
        },
    )
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]
    assert created.json()["name"] == target["name"]

    still_there = (await http.get(f"/api/v1/public/r/{token}/employees")).json()
    assert any(e["id"] == target["id"] for e in still_there)

    approved = await http.post(
        f"/api/v1/employee-changes/{request_id}/approve", headers=auth_headers
    )
    assert approved.status_code == 200, approved.text

    after = (await http.get(f"/api/v1/public/r/{token}/employees")).json()
    assert not any(e["id"] == target["id"] for e in after)


@pytest.mark.asyncio
async def test_reject_leaves_master_untouched(http: AsyncClient, auth_headers: dict):
    client_id = await _client_id(http, auth_headers, 2)
    token = await _portal_token(http, auth_headers, client_id)

    request_id = (
        await http.post(
            f"/api/v1/public/r/{token}/employee-change",
            json={"change_type": "HIRE", "name": "반려될사람"},
        )
    ).json()["id"]

    rejected = await http.post(
        f"/api/v1/employee-changes/{request_id}/reject", headers=auth_headers
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"
    assert "반려될사람" not in await _employee_names(http, auth_headers, client_id)

    # 두 번 처리되지 않는다.
    again = await http.post(
        f"/api/v1/employee-changes/{request_id}/approve", headers=auth_headers
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_hire_without_name_is_rejected(http: AsyncClient, auth_headers: dict):
    client_id = await _client_id(http, auth_headers, 3)
    token = await _portal_token(http, auth_headers, client_id)
    r = await http.post(
        f"/api/v1/public/r/{token}/employee-change",
        json={"change_type": "HIRE", "name": "   "},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cannot_resign_another_clients_employee(http: AsyncClient, auth_headers: dict):
    """다른 거래처 직원 id를 넣어도 통하지 않는다."""
    a_id = await _client_id(http, auth_headers, 4)
    b_id = await _client_id(http, auth_headers, 5)
    a_token = await _portal_token(http, auth_headers, a_id)
    b_token = await _portal_token(http, auth_headers, b_id)

    b_roster = (await http.get(f"/api/v1/public/r/{b_token}/employees")).json()
    assert len(b_roster) > 0

    r = await http.post(
        f"/api/v1/public/r/{a_token}/employee-change",
        json={"change_type": "RESIGN", "employee_id": b_roster[0]["id"]},
    )
    assert r.status_code == 404
