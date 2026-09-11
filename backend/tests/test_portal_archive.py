"""보관함 — 월별 납부세액·접수증·가상계좌 (plan/12-owner-portal.md §3.4, §5.4).

검증 목표
1. 예상 납부세액은 저장값이 아니라 PayrollEntry 합계로 계산된다
2. 세무사가 PDF를 올리면 RPA 없이도 보관함이 돌아간다
3. 링크가 유효해야만 서류를 받을 수 있다
"""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient

_PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


async def _client_id(http: AsyncClient, auth_headers: dict, index: int) -> str:
    clients = (await http.get("/api/v1/clients", headers=auth_headers)).json()
    return clients[index]["id"]


async def _portal_token(http: AsyncClient, auth_headers: dict, client_id: str) -> str:
    r = await http.get(f"/api/v1/clients/{client_id}/portal-link", headers=auth_headers)
    return r.json()["url"].rsplit("/", 1)[-1]


@pytest.mark.asyncio
async def test_archive_estimates_tax_from_payroll(http: AsyncClient, auth_headers: dict):
    """신고 결과를 하나도 안 올렸어도 예상 납부세액은 보인다."""
    client_id = await _client_id(http, auth_headers, 0)
    token = await _portal_token(http, auth_headers, client_id)

    rows = (await http.get(f"/api/v1/public/r/{token}/archive")).json()
    assert len(rows) > 0
    periods = [row["period"] for row in rows]
    assert periods == sorted(periods, reverse=True)  # 최신 기간이 위로
    assert any(row["estimated_tax"] > 0 for row in rows)
    assert all(row["settled_tax"] is None for row in rows)
    assert all(row["has_receipt"] is False for row in rows)


@pytest.mark.asyncio
async def test_settled_amount_and_virtual_account_reach_the_owner(
    http: AsyncClient, auth_headers: dict
):
    client_id = await _client_id(http, auth_headers, 1)
    token = await _portal_token(http, auth_headers, client_id)

    saved = await http.put(
        f"/api/v1/clients/{client_id}/filing-results/2026-04",
        headers=auth_headers,
        json={
            "settled_tax": 1_240_300,
            "virtual_account": "국민 123456-99-000001",
            "epayment_number": "1234567890123",
            "due_date": "2026-05-11",
        },
    )
    assert saved.status_code == 200, saved.text

    rows = (await http.get(f"/api/v1/public/r/{token}/archive")).json()
    april = next(row for row in rows if row["period"] == "2026-04")
    assert april["settled_tax"] == 1_240_300
    assert april["virtual_account"] == "국민 123456-99-000001"
    assert april["due_date"] == "2026-05-11"


@pytest.mark.asyncio
async def test_receipt_upload_then_owner_download(http: AsyncClient, auth_headers: dict):
    """RPA 없이 세무사 업로드만으로 보관함이 성립한다."""
    client_id = await _client_id(http, auth_headers, 2)
    token = await _portal_token(http, auth_headers, client_id)

    # 올리기 전에는 받을 게 없다.
    assert (
        await http.get(f"/api/v1/public/r/{token}/archive/2026-03/receipt")
    ).status_code == 404

    uploaded = await http.post(
        f"/api/v1/clients/{client_id}/filing-results/2026-03/documents/receipt",
        headers=auth_headers,
        files={"file": ("접수증.pdf", io.BytesIO(_PDF), "application/pdf")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["has_receipt"] is True

    rows = (await http.get(f"/api/v1/public/r/{token}/archive")).json()
    march = next(row for row in rows if row["period"] == "2026-03")
    assert march["has_receipt"] is True
    assert march["has_payment_slip"] is False

    got = await http.get(f"/api/v1/public/r/{token}/archive/2026-03/receipt")
    assert got.status_code == 200, got.text
    assert got.headers["content-type"] == "application/pdf"
    assert got.content == _PDF


@pytest.mark.asyncio
async def test_tax_office_sees_same_archive_as_owner(http: AsyncClient, auth_headers: dict):
    """세무사 보관함 목록은 사장님 화면과 같은 데이터여야 한다 — 어긋나면 채울 칸을 못 찾는다."""
    client_id = await _client_id(http, auth_headers, 4)
    token = await _portal_token(http, auth_headers, client_id)

    await http.put(
        f"/api/v1/clients/{client_id}/filing-results/2026-04",
        headers=auth_headers,
        json={"settled_tax": 777_000, "due_date": "2026-05-11"},
    )

    mine = await http.get(f"/api/v1/clients/{client_id}/filing-results", headers=auth_headers)
    assert mine.status_code == 200, mine.text
    owner = (await http.get(f"/api/v1/public/r/{token}/archive")).json()
    assert mine.json() == owner

    april = next(row for row in mine.json() if row["period"] == "2026-04")
    assert april["settled_tax"] == 777_000


@pytest.mark.asyncio
async def test_archive_list_requires_auth(http: AsyncClient):
    client_id = "whatever"
    assert (await http.get(f"/api/v1/clients/{client_id}/filing-results")).status_code == 401


@pytest.mark.asyncio
async def test_non_pdf_upload_is_rejected(http: AsyncClient, auth_headers: dict):
    client_id = await _client_id(http, auth_headers, 3)
    r = await http.post(
        f"/api/v1/clients/{client_id}/filing-results/2026-03/documents/receipt",
        headers=auth_headers,
        files={"file": ("접수증.png", io.BytesIO(b"not-a-pdf"), "image/png")},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_bad_period_is_rejected(http: AsyncClient, auth_headers: dict):
    client_id = await _client_id(http, auth_headers, 3)
    r = await http.put(
        f"/api/v1/clients/{client_id}/filing-results/2026-4",
        headers=auth_headers,
        json={"settled_tax": 100},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_archive_requires_valid_link(http: AsyncClient):
    assert (await http.get("/api/v1/public/r/nope/archive")).status_code == 404
    assert (
        await http.get("/api/v1/public/r/nope/archive/2026-03/receipt")
    ).status_code == 404
