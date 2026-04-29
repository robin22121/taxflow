"""End-to-end smoke test using a fresh SQLite DB seeded by conftest."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_and_list_filings(http: AsyncClient, auth_headers: dict):
    r = await http.get("/api/v1/filings", headers=auth_headers)
    assert r.status_code == 200, r.text
    periods = [f["period"] for f in r.json()]
    assert "2026-03" in periods
    assert "2026-04" in periods


@pytest.mark.asyncio
async def test_dashboard_shows_anomalies(http: AsyncClient, auth_headers: dict):
    filings = (await http.get("/api/v1/filings", headers=auth_headers)).json()
    apr = next(f for f in filings if f["period"] == "2026-04")
    r = await http.get(f"/api/v1/filings/{apr['id']}/dashboard", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data["sessions"]) == 3
    assert any(s["has_anomalies"] for s in data["sessions"])


@pytest.mark.asyncio
async def test_excel_download_for_approved_filing(http: AsyncClient, auth_headers: dict):
    filings = (await http.get("/api/v1/filings", headers=auth_headers)).json()
    march = next(f for f in filings if f["period"] == "2026-03")
    r = await http.get(f"/api/v1/filings/{march['id']}/wehago-excel", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert len(r.content) > 1000


@pytest.mark.asyncio
async def test_unauth_blocks_filings(http: AsyncClient):
    r = await http.get("/api/v1/filings")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_clients_list(http: AsyncClient, auth_headers: dict):
    r = await http.get("/api/v1/clients", headers=auth_headers)
    assert r.status_code == 200
    names = [c["business_name"] for c in r.json()]
    assert len(names) == 3
    assert "(주)에이상사" in names


@pytest.mark.asyncio
async def test_public_session_resolution(http: AsyncClient, auth_headers: dict):
    """A non-authenticated visitor with a session token sees client + period."""
    filings = (await http.get("/api/v1/filings", headers=auth_headers)).json()
    apr = next(f for f in filings if f["period"] == "2026-04")
    dash = (await http.get(f"/api/v1/filings/{apr['id']}/dashboard", headers=auth_headers)).json()
    token = dash["sessions"][0]["request_token"]

    r = await http.get(f"/api/v1/public/r/{token}")  # NO auth header
    assert r.status_code == 200
    assert r.json()["period"] == "2026-04"
    assert "client_name" in r.json()
