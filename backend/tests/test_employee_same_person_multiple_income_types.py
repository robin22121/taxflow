"""동일인이 소득유형별로 여러 줄로 나뉠 때 화면에 알려주기 — plan/16 §12-2-1 "동일인 다중등록"."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_other_income_types_lists_same_rrn_peers(http: AsyncClient, auth_headers: dict):
    cid = (await http.get("/api/v1/clients", headers=auth_headers)).json()[0]["id"]
    base = f"/api/v1/clients/{cid}/employees"

    # 시드 데이터에 같은 주민번호가 이미 있을 수 있으니(다른 테스트와 공유하는 DB) 흔치 않은
    # 번호를 쓴다 — 매칭 로직 자체(겹치는 소득유형만 표시)만 확인하면 된다.
    shared_rrn = "931231-2098765"
    wage = (
        await http.post(base, json={"name": "겸업직원", "rrn": shared_rrn, "income_type": "WAGE"}, headers=auth_headers)
    ).json()
    business = (
        await http.post(
            base, json={"name": "겸업직원", "rrn": shared_rrn, "income_type": "BUSINESS"}, headers=auth_headers
        )
    ).json()
    unrelated = (
        await http.post(base, json={"name": "다른사람", "rrn": "850505-2345678", "income_type": "WAGE"}, headers=auth_headers)
    ).json()

    rows = {e["id"]: e for e in (await http.get(base, headers=auth_headers)).json()}
    assert "BUSINESS" in rows[wage["id"]]["other_income_types"]
    assert "WAGE" not in rows[wage["id"]]["other_income_types"]  # 본인 소득유형은 제외
    assert "WAGE" in rows[business["id"]]["other_income_types"]
    assert rows[unrelated["id"]]["other_income_types"] == []
