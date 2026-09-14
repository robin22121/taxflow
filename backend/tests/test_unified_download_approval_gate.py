"""통합 다운로드 — 미승인 엔트리가 있는 거래처는 받을 수 없다."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _client_with_unapproved(http: AsyncClient, auth_headers: dict) -> tuple[str, str]:
    """시드 데이터에서 (filing_id, 미승인 엔트리가 있는 client_id) 하나를 찾는다."""
    filings = (await http.get("/api/v1/filings", headers=auth_headers)).json()
    for filing in filings:
        entries = (
            await http.get(f"/api/v1/filings/{filing['id']}/entries", headers=auth_headers)
        ).json()
        for entry in entries:
            if not entry["approved"]:
                return filing["id"], entry["client_id"]
    pytest.skip("시드에 미승인 급여항목이 없다")


@pytest.mark.asyncio
async def test_unapproved_client_is_blocked_until_approved(http: AsyncClient, auth_headers: dict):
    filing_id, client_id = await _client_with_unapproved(http, auth_headers)

    res = await http.get(
        f"/api/v1/filings/{filing_id}/unified-download",
        params={"client_ids": client_id},
        headers=auth_headers,
    )
    assert res.status_code == 409, res.text
    assert "미승인" in res.json()["detail"]

    entries = (
        await http.get(f"/api/v1/filings/{filing_id}/entries", headers=auth_headers)
    ).json()
    for entry in entries:
        if entry["client_id"] == client_id and not entry["approved"]:
            r = await http.patch(
                f"/api/v1/filings/{filing_id}/entries/{entry['id']}",
                json={"approved": True},
                headers=auth_headers,
            )
            assert r.status_code == 200, r.text

    res = await http.get(
        f"/api/v1/filings/{filing_id}/unified-download",
        params={"client_ids": client_id},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/zip"


@pytest.mark.asyncio
async def test_client_without_entries_is_blocked(http: AsyncClient, auth_headers: dict):
    filing = (await http.get("/api/v1/filings", headers=auth_headers)).json()[0]
    created = await http.post(
        "/api/v1/clients", json={"business_name": "자료없는상사"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text

    res = await http.get(
        f"/api/v1/filings/{filing['id']}/unified-download",
        params={"client_ids": created.json()["id"]},
        headers=auth_headers,
    )
    assert res.status_code == 409, res.text
    assert "자료가 없는" in res.json()["detail"]
