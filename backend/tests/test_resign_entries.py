"""퇴사처리 — 선택한 급여항목의 직원만 RESIGNED 로 바꾸고 항목은 남긴다."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _first_entry_with_employee(http: AsyncClient, auth_headers: dict) -> tuple[str, str]:
    """시드 데이터에서 (filing_id, 직원이 매칭된 entry_id) 하나를 찾는다."""
    filings = (await http.get("/api/v1/filings", headers=auth_headers)).json()
    for filing in filings:
        entries = (
            await http.get(f"/api/v1/filings/{filing['id']}/entries", headers=auth_headers)
        ).json()
        for entry in entries:
            if entry.get("employee_id"):
                return filing["id"], entry["id"]
    pytest.skip("시드에 직원이 매칭된 급여항목이 없다")


@pytest.mark.asyncio
async def test_resign_keeps_entry_and_marks_employee(http: AsyncClient, auth_headers: dict):
    filing_id, entry_id = await _first_entry_with_employee(http, auth_headers)

    res = await http.post(
        f"/api/v1/filings/{filing_id}/entries/resign",
        json={"entry_ids": [entry_id], "resigned_at": "2026-09-30"},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    assert len(res.json()["resigned"]) == 1

    # 급여항목은 남아 있어야 한다 — 퇴사한 달도 신고 대상
    entries = (
        await http.get(f"/api/v1/filings/{filing_id}/entries", headers=auth_headers)
    ).json()
    assert any(e["id"] == entry_id for e in entries)


@pytest.mark.asyncio
async def test_resign_twice_is_reported_as_skipped(http: AsyncClient, auth_headers: dict):
    filing_id, entry_id = await _first_entry_with_employee(http, auth_headers)
    body = {"entry_ids": [entry_id], "resigned_at": "2026-09-30"}

    await http.post(f"/api/v1/filings/{filing_id}/entries/resign", json=body, headers=auth_headers)
    again = await http.post(
        f"/api/v1/filings/{filing_id}/entries/resign", json=body, headers=auth_headers
    )
    assert again.status_code == 200
    assert again.json()["resigned"] == []
    assert len(again.json()["skipped"]) == 1


@pytest.mark.asyncio
async def test_unknown_entry_is_404(http: AsyncClient, auth_headers: dict):
    filing_id, _ = await _first_entry_with_employee(http, auth_headers)
    res = await http.post(
        f"/api/v1/filings/{filing_id}/entries/resign",
        json={"entry_ids": ["does-not-exist"], "resigned_at": "2026-09-30"},
        headers=auth_headers,
    )
    assert res.status_code == 404
