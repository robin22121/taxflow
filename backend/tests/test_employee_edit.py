"""거래처 직원 수정 + 사원코드 기본 숫자 번호 (위하고 사원코드와 같게, 2026-09-27)."""

import pytest
from httpx import AsyncClient


async def _client_id(http: AsyncClient, auth_headers: dict) -> str:
    return (await http.get("/api/v1/clients", headers=auth_headers)).json()[0]["id"]


@pytest.mark.asyncio
async def test_blank_code_gets_next_number_and_employee_can_be_edited(http: AsyncClient, auth_headers: dict):
    cid = await _client_id(http, auth_headers)
    base = f"/api/v1/clients/{cid}/employees"
    existing = (await http.get(base, headers=auth_headers)).json()
    numbers = [int(e["employee_code"]) for e in existing if (e["employee_code"] or "").isdigit()]
    expected = str(max(numbers, default=0) + 1)

    r = await http.post(base, json={"name": "코드테스트"}, headers=auth_headers)
    assert r.status_code == 201, r.text
    emp = r.json()
    assert emp["employee_code"] == expected

    r = await http.patch(f"{base}/{emp['id']}", json={"name": "코드수정", "department": "관리", "employee_code": " 900 "}, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert (r.json()["name"], r.json()["department"], r.json()["employee_code"]) == ("코드수정", "관리", "900")

    other = (await http.post(base, json={"name": "다른직원"}, headers=auth_headers)).json()
    assert other["employee_code"] == "901"  # 가장 큰 숫자 코드(900) + 1

    dup = await http.patch(f"{base}/{other['id']}", json={"employee_code": "900"}, headers=auth_headers)
    assert dup.status_code == 409
    assert "이미 같은 소득구분" in dup.json()["detail"]


@pytest.mark.asyncio
async def test_same_number_allowed_across_different_income_types(http: AsyncClient, auth_headers: dict):
    """근로1·사업1·기타1처럼 소득구분이 다르면 같은 사원코드 번호를 써도 된다."""
    cid = await _client_id(http, auth_headers)
    base = f"/api/v1/clients/{cid}/employees"

    # 다른 테스트가 이미 써버렸을 수 있는 숫자와 겹치지 않도록, 전 소득구분에서 비어 있는
    # 번호를 하나 골라 근로/사업/기타 세 소득구분에 동시에 쓴다.
    existing = (await http.get(base, headers=auth_headers)).json()
    used = {int(e["employee_code"]) for e in existing if (e["employee_code"] or "").isdigit()}
    code = str(max(used, default=0) + 1)

    for income_type, name in (("WAGE", "근로"), ("BUSINESS", "사업"), ("OTHER", "기타")):
        r = await http.post(
            base, json={"name": name, "employee_code": code, "income_type": income_type}, headers=auth_headers
        )
        assert r.status_code == 201, r.text
        assert r.json()["employee_code"] == code

    # 같은 소득구분(WAGE) 안에서는 여전히 중복이 막힌다.
    dup_wage = await http.post(
        base, json={"name": "근로-중복", "employee_code": code, "income_type": "WAGE"}, headers=auth_headers
    )
    assert dup_wage.status_code == 409
