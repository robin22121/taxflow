"""사장님 포털 '직원 골라 금액 변경' 제출 + 항목별 변동 계산 근거 (plan/12-owner-portal.md §8.3).

AI를 거치지 않는 경로라 서버만으로 끝까지 검증할 수 있다.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import AsyncClient


async def _portal(http: AsyncClient, auth_headers: dict) -> tuple[str, str, str]:
    filings = (await http.get("/api/v1/filings", headers=auth_headers)).json()
    apr = next(f for f in filings if f["period"] == "2026-04")
    clients = (await http.get("/api/v1/clients", headers=auth_headers)).json()
    client_id = clients[0]["id"]
    link = (
        await http.get(f"/api/v1/clients/{client_id}/portal-link", headers=auth_headers)
    ).json()
    return apr["id"], client_id, link["url"].rsplit("/", 1)[-1]


async def _client_entries(
    http: AsyncClient, auth_headers: dict, filing_id: str, client_id: str
) -> list[dict]:
    entries = (
        await http.get(f"/api/v1/filings/{filing_id}/entries", headers=auth_headers)
    ).json()
    return [e for e in entries if e["client_id"] == client_id]


async def _active_ids(http: AsyncClient, token: str) -> set[str]:
    rows = (await http.get(f"/api/v1/public/r/{token}/employees-v2")).json()
    return {r["id"] for r in rows if r["status"] == "ACTIVE"}


@pytest.mark.asyncio
async def test_pick_amount_updates_only_picked_employee(http: AsyncClient, auth_headers: dict):
    """고른 직원만 새 금액으로 갱신되고, 이미 있는 나머지 항목은 그대로다."""
    filing_id, client_id, token = await _portal(http, auth_headers)
    active = await _active_ids(http, token)
    before = await _client_entries(http, auth_headers, filing_id, client_id)
    target = next(e for e in before if e["employee_id"] in active)
    others = {e["id"]: e["total_amount"] for e in before if e["id"] != target["id"]}
    new_amount = target["total_amount"] + 100_000

    r = await http.post(
        f"/api/v1/public/r/{token}/submit-amounts",
        json={"items": [{"employee_id": target["employee_id"], "total_amount": new_amount}]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 1

    after = {e["id"]: e for e in await _client_entries(http, auth_headers, filing_id, client_id)}
    assert after[target["id"]]["total_amount"] == new_amount
    assert after[target["id"]]["approved"] is False
    assert after[target["id"]]["source_event"]["channel"] == "public_select"
    assert {i: e["total_amount"] for i, e in after.items() if i != target["id"]} == others


@pytest.mark.asyncio
async def test_same_as_last_month_carries_missing_employee(http: AsyncClient, auth_headers: dict):
    """항목 없이 보내면(지난달과 동일) 이번 달에 빠진 직원을 지난달 금액 그대로 옮긴다."""
    filing_id, client_id, token = await _portal(http, auth_headers)
    active = await _active_ids(http, token)
    before = await _client_entries(http, auth_headers, filing_id, client_id)
    victim = next(e for e in before if e["employee_id"] in active and e["prev_amount"])
    deleted = await http.delete(
        f"/api/v1/filings/{filing_id}/entries/{victim['id']}", headers=auth_headers
    )
    assert deleted.status_code in (200, 204), deleted.text

    r = await http.post(f"/api/v1/public/r/{token}/submit-amounts", json={"items": []})
    assert r.status_code == 200, r.text

    after = await _client_entries(http, auth_headers, filing_id, client_id)
    restored = next(e for e in after if e["employee_id"] == victim["employee_id"])
    assert restored["source_event"]["channel"] == "public_same"
    assert restored["total_amount"] == restored["prev_amount"]
    assert len(after) == len(before)


@pytest.mark.asyncio
async def test_pick_amount_rejects_unknown_employee(http: AsyncClient, auth_headers: dict):
    _, _, token = await _portal(http, auth_headers)
    r = await http.post(
        f"/api/v1/public/r/{token}/submit-amounts",
        json={"items": [{"employee_id": "not-an-employee", "total_amount": 1_000_000}]},
    )
    assert r.status_code == 400, r.text


def test_insurance_change_records_rate_basis():
    """보수월액×요율로 계산한 4대보험 변동은 근거(과세급여·요율·전월 과세급여)를 남긴다."""
    from app.api.collect import _detect_field_anomalies
    from app.services.payroll_defaults import ResolvedPayrollDefaults

    prev = SimpleNamespace(
        national_pension=153_000, health_insurance=120_530, income_tax=None, taxable=3_400_000
    )
    cand = SimpleNamespace(national_pension=None, health_insurance=None)
    anomaly: dict = {}
    _detect_field_anomalies(
        anomaly, cand, prev, 0,
        144_000, 113_440, 0, 0,
        taxable=3_200_000,
        defaults=ResolvedPayrollDefaults(),
    )

    fc = anomaly["field_changes"]
    assert fc["health_insurance"] == {
        "prev": 120_530,
        "curr": 113_440,
        "prev_base": 3_400_000,
        "source": "computed",
        "base": 3_200_000,
        "rate": 0.03545,
    }
    assert fc["national_pension"]["base"] == 3_200_000
    assert fc["national_pension"]["rate"] == 0.045


def test_insurance_change_from_source_value_is_marked_raw():
    """제출 자료에 적힌 공제액을 그대로 쓴 경우는 요율 근거 대신 raw로 표시한다."""
    from app.api.collect import _detect_field_anomalies
    from app.services.payroll_defaults import ResolvedPayrollDefaults

    prev = SimpleNamespace(
        national_pension=0, health_insurance=120_530, income_tax=None, taxable=3_400_000
    )
    cand = SimpleNamespace(national_pension=None, health_insurance=113_440)
    anomaly: dict = {}
    _detect_field_anomalies(
        anomaly, cand, prev, 0,
        0, 113_440, 0, 0,
        taxable=3_200_000,
        defaults=ResolvedPayrollDefaults(),
    )

    assert anomaly["field_changes"]["health_insurance"]["source"] == "raw"
    assert "rate" not in anomaly["field_changes"]["health_insurance"]
