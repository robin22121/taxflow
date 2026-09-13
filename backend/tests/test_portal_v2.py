"""§8 리디자인 — 4개 신규 엔드포인트 (plan/12-owner-portal.md §8.11.1).

- /status : 5-단계 상태 + 예상 세액 + 세무사무소 이름
- /last-month : 지난달 요약 (공개) + 개별 명세 (PIN 뒤)
- /monthly-cost : 12개월 소득종류별 스택
- /employees/{id} : 직원 상세 (급여 이력은 PIN 뒤)
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
    return r.json()["pin"]


async def _grant(http: AsyncClient, token: str, pin: str) -> str:
    r = await http.post(f"/api/v1/public/r/{token}/unlock", json={"pin": pin})
    assert r.status_code == 200, r.text
    return r.json()["grant"]


@pytest.mark.asyncio
async def test_status_returns_5_state_and_tax_office(
    http: AsyncClient, auth_headers: dict
):
    """상태 스트립·납부 카드가 한 번의 GET으로 렌더할 수 있어야 한다."""
    client_id = await _client_id(http, auth_headers, 0)
    token = await _portal_token(http, auth_headers, client_id)

    r = await http.get(f"/api/v1/public/r/{token}/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] in {"NONE", "COLLECTING", "REVIEWING", "FILED", "PAID", "OVERDUE"}
    assert body["tax_office_name"]  # 헤더에 표시
    assert body["estimated_tax"] >= 0
    # 열린 신고가 있다면 period도 함께
    if body["state"] != "NONE":
        assert body["period"]


@pytest.mark.asyncio
async def test_status_bad_link_is_404(http: AsyncClient):
    assert (await http.get("/api/v1/public/r/nope/status")).status_code == 404


@pytest.mark.asyncio
async def test_last_month_summary_public_details_gated(
    http: AsyncClient, auth_headers: dict
):
    """지난달 합계는 공개, 개별 직원 명세는 PIN 뒤."""
    client_id = await _client_id(http, auth_headers, 1)
    token = await _portal_token(http, auth_headers, client_id)

    public = (await http.get(f"/api/v1/public/r/{token}/last-month")).json()
    # 합계는 노출된다 (0일 수 있음 — 데이터가 없을 수도)
    assert "employee_count" in public
    assert public["entries"] is None  # 게이트 앞에서는 개별 명세 숨김

    pin = await _issue_pin(http, auth_headers, client_id)
    grant = await _grant(http, token, pin)
    private = (
        await http.get(
            f"/api/v1/public/r/{token}/last-month",
            headers={"X-Portal-Grant": grant},
        )
    ).json()
    # 명세는 데이터가 있을 때만 채워진다. 빈 리스트라도 None이 아니어야 게이트 뒤임을 의미
    assert private["entries"] is not None


@pytest.mark.asyncio
async def test_monthly_cost_returns_series_and_kpis(
    http: AsyncClient, auth_headers: dict
):
    """12개월 스택 시리즈 + KPI가 최소 형태를 갖춘다."""
    client_id = await _client_id(http, auth_headers, 2)
    token = await _portal_token(http, auth_headers, client_id)

    r = await http.get(f"/api/v1/public/r/{token}/monthly-cost?months=12")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["series"]) == 12
    assert set(body["series"][0].keys()) >= {
        "period", "wage", "business", "daily", "other", "total",
    }
    assert set(body["kpis"].keys()) == {"total", "monthly_avg", "yoy_pct"}


@pytest.mark.asyncio
async def test_monthly_cost_rejects_bad_months(
    http: AsyncClient, auth_headers: dict
):
    client_id = await _client_id(http, auth_headers, 3)
    token = await _portal_token(http, auth_headers, client_id)
    assert (
        await http.get(f"/api/v1/public/r/{token}/monthly-cost?months=7")
    ).status_code == 400


@pytest.mark.asyncio
async def test_employees_v2_lists_active_and_optionally_resigned(
    http: AsyncClient, auth_headers: dict
):
    client_id = await _client_id(http, auth_headers, 4)
    token = await _portal_token(http, auth_headers, client_id)

    active = (await http.get(f"/api/v1/public/r/{token}/employees-v2")).json()
    assert isinstance(active, list)
    # 재직자만 나와야 한다
    assert all(row["status"] == "ACTIVE" for row in active)

    both = (
        await http.get(
            f"/api/v1/public/r/{token}/employees-v2?include_resigned=true"
        )
    ).json()
    # 퇴사자 포함하면 개수가 같거나 늘어난다
    assert len(both) >= len(active)


@pytest.mark.asyncio
async def test_employee_detail_gated_history(
    http: AsyncClient, auth_headers: dict
):
    """이름·직위 같은 기본 정보는 공개, 급여 이력·KPI는 PIN 뒤."""
    client_id = await _client_id(http, auth_headers, 0)
    token = await _portal_token(http, auth_headers, client_id)

    employees = (await http.get(f"/api/v1/public/r/{token}/employees-v2")).json()
    assert employees, "seed에 직원이 있어야 이 테스트가 성립한다"
    employee_id = employees[0]["id"]

    public = (
        await http.get(f"/api/v1/public/r/{token}/employees/{employee_id}")
    ).json()
    assert public["name"]
    assert public["history"] is None
    assert public["total_ytd"] is None

    pin = await _issue_pin(http, auth_headers, client_id)
    grant = await _grant(http, token, pin)
    private = (
        await http.get(
            f"/api/v1/public/r/{token}/employees/{employee_id}",
            headers={"X-Portal-Grant": grant},
        )
    ).json()
    assert private["history"] is not None
    assert private["total_ytd"] is not None


@pytest.mark.asyncio
async def test_employee_detail_wrong_client_is_404(
    http: AsyncClient, auth_headers: dict
):
    """다른 거래처 링크로 남의 직원 조회하면 404."""
    a_client = await _client_id(http, auth_headers, 0)
    b_client = await _client_id(http, auth_headers, 1)
    a_token = await _portal_token(http, auth_headers, a_client)

    b_employees = (
        await http.get(
            f"/api/v1/public/r/{await _portal_token(http, auth_headers, b_client)}/employees-v2"
        )
    ).json()
    if not b_employees:
        pytest.skip("seed에 b 거래처 직원이 없음")
    other_id = b_employees[0]["id"]

    r = await http.get(f"/api/v1/public/r/{a_token}/employees/{other_id}")
    assert r.status_code == 404
