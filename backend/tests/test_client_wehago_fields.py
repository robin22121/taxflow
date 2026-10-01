"""거래처의 위하고 참고 필드(업태·종목·사업장주소·관할세무서) 노출 — plan/16 §12-2."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_client_wehago_fields_round_trip(http: AsyncClient, auth_headers: dict):
    clients = (await http.get("/api/v1/clients", headers=auth_headers)).json()
    client_id = clients[0]["id"]

    patch = {
        "business_type": "부동산업",
        "business_item": "비주거용 건물 임대업",
        "business_address": "강원특별자치도 횡성군 횡성읍 어사매로 68",
        "tax_jurisdiction": "원주 세무서",
    }
    r = await http.patch(f"/api/v1/clients/{client_id}", json=patch, headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    for key, value in patch.items():
        assert body[key] == value

    fetched = (await http.get("/api/v1/clients", headers=auth_headers)).json()
    row = next(c for c in fetched if c["id"] == client_id)
    for key, value in patch.items():
        assert row.get(key) == value
