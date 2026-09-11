"""거래처별 전체 월 급여 이력 조회 — GET /clients/{id}/payroll-history."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _client_with_history(http: AsyncClient, auth_headers: dict) -> dict:
    clients = (await http.get("/api/v1/clients", headers=auth_headers)).json()
    for c in clients:
        r = await http.get(
            f"/api/v1/clients/{c['id']}/payroll-history", headers=auth_headers
        )
        assert r.status_code == 200, r.text
        if r.json():
            return {"client": c, "history": r.json()}
    pytest.fail("급여 이력이 있는 거래처가 시드에 없습니다")


@pytest.mark.asyncio
async def test_returns_all_months_newest_first(http: AsyncClient, auth_headers: dict):
    history = (await _client_with_history(http, auth_headers))["history"]

    periods = [p["period"] for p in history]
    assert len(periods) > 1, "시드는 여러 달 이력을 갖는다"
    assert periods == sorted(periods, reverse=True)


@pytest.mark.asyncio
async def test_period_totals_match_rows(http: AsyncClient, auth_headers: dict):
    history = (await _client_with_history(http, auth_headers))["history"]

    for p in history:
        assert p["employee_count"] == len(p["rows"])
        assert p["total_amount"] == sum(r["total_amount"] for r in p["rows"])
        assert p["total_non_taxable"] == sum(r["non_taxable"] for r in p["rows"])
        assert p["total_income_tax"] == sum(r["income_tax"] for r in p["rows"])


@pytest.mark.asyncio
async def test_matches_filing_entries_for_same_period(
    http: AsyncClient, auth_headers: dict
):
    """filing 화면이 보여주는 엔트리와 같은 자료를 보여야 한다."""
    found = await _client_with_history(http, auth_headers)
    client_id = found["client"]["id"]
    period = found["history"][0]

    entries = (
        await http.get(
            f"/api/v1/filings/{period['filing_id']}/entries", headers=auth_headers
        )
    ).json()
    same_client = [e for e in entries if e["client_id"] == client_id]

    assert period["employee_count"] == len(same_client)
    assert period["total_amount"] == sum(e["total_amount"] for e in same_client)


@pytest.mark.asyncio
async def test_other_office_client_is_404(http: AsyncClient, auth_headers: dict):
    r = await http.get(
        "/api/v1/clients/does-not-exist/payroll-history", headers=auth_headers
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_requires_auth(http: AsyncClient):
    r = await http.get("/api/v1/clients/whatever/payroll-history")
    assert r.status_code == 401
