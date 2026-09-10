"""PIN 게이트 — 민감 구역 열람 통제 (plan/12-owner-portal.md §4.3.3).

검증 목표
1. PIN 미발급 거래처는 게이트 뒤 구역이 아예 없다
2. 올바른 PIN만 grant를 받고, grant 없이는 금액을 볼 수 없다
3. 5회 실패하면 잠기고, 재발급하면 풀린다
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _client_id(http: AsyncClient, auth_headers: dict, index: int) -> str:
    clients = (await http.get("/api/v1/clients", headers=auth_headers)).json()
    return clients[index]["id"]


async def _portal_token(http: AsyncClient, auth_headers: dict, client_id: str) -> str:
    r = await http.get(f"/api/v1/clients/{client_id}/portal-link", headers=auth_headers)
    return r.json()["url"].rsplit("/", 1)[-1]


async def _issue_pin(http: AsyncClient, auth_headers: dict, client_id: str) -> str:
    r = await http.post(f"/api/v1/clients/{client_id}/portal-pin", headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["pin"]


@pytest.mark.asyncio
async def test_gate_absent_when_pin_not_issued(http: AsyncClient, auth_headers: dict):
    """PIN 미발급이면 게이트 뒤 구역을 노출하지 않는다 — 잠긴 화면조차 보여주지 않는다."""
    client_id = await _client_id(http, auth_headers, 2)
    token = await _portal_token(http, auth_headers, client_id)

    status_r = await http.get(f"/api/v1/clients/{client_id}/portal-pin", headers=auth_headers)
    assert status_r.json()["is_set"] is False

    # 화면이 게이트를 아예 그리지 않도록 공개 응답이 알려준다.
    assert (await http.get(f"/api/v1/public/r/{token}")).json()["has_pin"] is False

    assert (await http.post(f"/api/v1/public/r/{token}/unlock", json={"pin": "123456"})).status_code == 404
    assert (await http.get(f"/api/v1/public/r/{token}/payroll")).status_code == 401


@pytest.mark.asyncio
async def test_correct_pin_opens_payroll(http: AsyncClient, auth_headers: dict):
    """올바른 PIN → grant → 직원별 금액 열람."""
    client_id = await _client_id(http, auth_headers, 3)
    token = await _portal_token(http, auth_headers, client_id)
    pin = await _issue_pin(http, auth_headers, client_id)

    assert (await http.get(f"/api/v1/public/r/{token}")).json()["has_pin"] is True
    assert (await http.get(f"/api/v1/public/r/{token}/payroll")).status_code == 401

    unlocked = await http.post(f"/api/v1/public/r/{token}/unlock", json={"pin": pin})
    assert unlocked.status_code == 200, unlocked.text
    grant = unlocked.json()["grant"]
    assert unlocked.json()["expires_in"] > 0

    rows = await http.get(
        f"/api/v1/public/r/{token}/payroll", headers={"X-Portal-Grant": grant}
    )
    assert rows.status_code == 200, rows.text
    body = rows.json()
    assert len(body) > 0
    assert all("name" in row and "total_amount" in row for row in body)
    assert any(row["prev_amount"] is not None for row in body)


@pytest.mark.asyncio
async def test_wrong_pin_is_rejected(http: AsyncClient, auth_headers: dict):
    client_id = await _client_id(http, auth_headers, 4)
    token = await _portal_token(http, auth_headers, client_id)
    pin = await _issue_pin(http, auth_headers, client_id)
    wrong = "000000" if pin != "000000" else "111111"

    r = await http.post(f"/api/v1/public/r/{token}/unlock", json={"pin": wrong})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_grant_of_other_client_is_rejected(http: AsyncClient, auth_headers: dict):
    """다른 거래처에서 받은 grant로는 열 수 없다."""
    a_id = await _client_id(http, auth_headers, 5)
    b_id = await _client_id(http, auth_headers, 6)
    a_token = await _portal_token(http, auth_headers, a_id)
    b_token = await _portal_token(http, auth_headers, b_id)
    a_pin = await _issue_pin(http, auth_headers, a_id)
    await _issue_pin(http, auth_headers, b_id)

    a_grant = (
        await http.post(f"/api/v1/public/r/{a_token}/unlock", json={"pin": a_pin})
    ).json()["grant"]

    cross = await http.get(
        f"/api/v1/public/r/{b_token}/payroll", headers={"X-Portal-Grant": a_grant}
    )
    assert cross.status_code == 401


@pytest.mark.asyncio
async def test_five_failures_lock_then_reissue_unlocks(http: AsyncClient, auth_headers: dict):
    """5회 실패 시 잠기고, 올바른 PIN도 막힌다. 재발급하면 풀린다 (§4.3.3)."""
    client_id = await _client_id(http, auth_headers, 1)
    token = await _portal_token(http, auth_headers, client_id)
    pin = await _issue_pin(http, auth_headers, client_id)
    wrong = "000000" if pin != "000000" else "111111"

    for _ in range(5):
        r = await http.post(f"/api/v1/public/r/{token}/unlock", json={"pin": wrong})
        assert r.status_code == 401, r.text

    locked = await http.post(f"/api/v1/public/r/{token}/unlock", json={"pin": pin})
    assert locked.status_code == 423, locked.text

    status_r = await http.get(f"/api/v1/clients/{client_id}/portal-pin", headers=auth_headers)
    assert status_r.json()["locked_until"] is not None

    new_pin = await _issue_pin(http, auth_headers, client_id)
    reopened = await http.post(f"/api/v1/public/r/{token}/unlock", json={"pin": new_pin})
    assert reopened.status_code == 200, reopened.text


@pytest.mark.asyncio
async def test_reissued_pin_invalidates_old_one(http: AsyncClient, auth_headers: dict):
    client_id = await _client_id(http, auth_headers, 0)
    token = await _portal_token(http, auth_headers, client_id)
    old_pin = await _issue_pin(http, auth_headers, client_id)
    new_pin = await _issue_pin(http, auth_headers, client_id)
    assert old_pin != new_pin

    assert (
        await http.post(f"/api/v1/public/r/{token}/unlock", json={"pin": old_pin})
    ).status_code == 401
    assert (
        await http.post(f"/api/v1/public/r/{token}/unlock", json={"pin": new_pin})
    ).status_code == 200
