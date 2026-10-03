"""고객이 보낸 원래 값(source_snapshot)과 수집 경로의 변경이력 — 수동 수정은 원본을 바꾸지 않는다."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select


async def _first_session() -> tuple[str, str, str]:
    from app.db import SessionLocal
    from app.models import CollectionSession

    async with SessionLocal() as db:
        s = (await db.execute(select(CollectionSession).limit(1))).scalar_one()
        return s.id, s.monthly_filing_id, s.client_id


async def _db_entry(entry_id: str):
    from app.db import SessionLocal
    from app.models import PayrollEntry

    async with SessionLocal() as db:
        return await db.get(PayrollEntry, entry_id)


async def _changes(http, headers, filing_id, entry_id, **params) -> list[dict]:
    r = await http.get(f"/api/v1/filings/{filing_id}/entry-changes",
                       params={"entry_id": entry_id, **params}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _body(items: list[dict]) -> dict:
    return {"text": "원본 보존 테스트", "channel": "manual", "sender_name": "테스터",
            "received_date": "2026-10-01", "entries": items}


def _item(total: int, **extra) -> dict:
    return {"raw_name": "원본보존테스트", "income_type": "WAGE", "total_amount": total,
            "match_status": "AMBIGUOUS", **extra}


async def _purge(entry_id: str) -> None:
    from app.db import SessionLocal
    from app.models import CollectionEvent, PayrollEntry, PayrollEntryChange

    async with SessionLocal() as db:
        entry = await db.get(PayrollEntry, entry_id)
        event_id = entry.collection_event_id if entry else None
        await db.execute(delete(PayrollEntryChange).where(PayrollEntryChange.entry_id == entry_id))
        await db.execute(delete(PayrollEntry).where(PayrollEntry.id == entry_id))
        if event_id:
            await db.execute(delete(CollectionEvent).where(CollectionEvent.id == event_id))
        await db.commit()


@pytest.mark.asyncio
async def test_collect_keeps_original_value_and_manual_edit_does_not_change_it(http: AsyncClient, auth_headers: dict):
    session_id, filing_id, client_id = await _first_session()
    entry_id = None
    try:
        # 1) 고객 자료 저장 → 원본 스냅샷 + CREATE 이력
        r = await http.post(f"/api/v1/collect/sessions/{session_id}/messages/commit",
                            headers=auth_headers, json=_body([_item(3_000_000)]))
        assert r.status_code == 200, r.text
        entries = (await http.get(f"/api/v1/filings/{filing_id}/entries", headers=auth_headers)).json()
        entry = next(e for e in entries if e["raw_name"] == "원본보존테스트" and e["client_id"] == client_id)
        entry_id = entry["id"]

        row = await _db_entry(entry_id)
        assert row.source_snapshot["source"] == "collect"
        assert row.source_snapshot["values"]["total_amount"] == 3_000_000

        created = [c for c in await _changes(http, auth_headers, filing_id, entry_id) if c["action"] == "CREATE"]
        assert len(created) == 1 and created[0]["source"] == "collect" and created[0]["actor_label"]

        # 2) 세무사가 원천세관리에서 수정 → 원본은 그대로, 이력만 쌓인다
        r = await http.patch(f"/api/v1/filings/{filing_id}/entries/{entry_id}", headers=auth_headers,
                             json={"total_amount": 3_200_000, "edit_reason": "고객 전화로 정정", "approved": True})
        assert r.status_code == 200, r.text
        row = await _db_entry(entry_id)
        assert row.total_amount == 3_200_000
        assert row.source_snapshot["values"]["total_amount"] == 3_000_000  # 받은 자료는 바뀌지 않는다

        # 3) 고객이 수정 메시지를 다시 보내면 "마지막으로 받은 값"으로 원본이 갱신되고 승인은 풀린다
        r = await http.post(
            f"/api/v1/collect/sessions/{session_id}/messages/commit", headers=auth_headers,
            json=_body([_item(3_500_000, mode="update", entry_id=entry_id)]),
        )
        assert r.status_code == 200, r.text
        row = await _db_entry(entry_id)
        assert row.total_amount == 3_500_000 and row.approved is False
        assert row.source_snapshot["values"]["total_amount"] == 3_500_000

        rows = await _changes(http, auth_headers, filing_id, entry_id, include_approvals="true")
        collect_update = next(c for c in rows if c["action"] == "UPDATE" and c["source"] == "collect")
        assert collect_update["changes"]["total_amount"]["before"] == 3_200_000  # 이전 값은 이력에 남는다
        assert any(c["action"] == "UNAPPROVE" and c["source"] == "collect" for c in rows)
    finally:
        if entry_id:
            await _purge(entry_id)


async def _portal_employee(http: AsyncClient, auth_headers: dict) -> tuple[str, str, str, str]:
    """포털로 금액을 보낼 수 있는 (신고 id, 거래처 id, 토큰, 재직 직원 id).

    포털은 "지금 열려 있는 가장 최근 신고"를 대상으로 하고 다른 테스트가 새 신고를 열 수 있어,
    신고 기간은 포털에 묻는다. 해당 신고에 항목이 있든 없든(갱신/생성) 쓸 수 있다.
    """
    filings = (await http.get("/api/v1/filings", headers=auth_headers)).json()
    for client in (await http.get("/api/v1/clients", headers=auth_headers)).json():
        link = (await http.get(f"/api/v1/clients/{client['id']}/portal-link", headers=auth_headers)).json()
        token = link["url"].rsplit("/", 1)[-1]
        period = (await http.get(f"/api/v1/public/r/{token}")).json()["period"]
        filing_id = next((f["id"] for f in filings if f["period"] == period), None)
        active = [r["id"] for r in (await http.get(f"/api/v1/public/r/{token}/employees-v2")).json()
                  if r["status"] == "ACTIVE"]
        if filing_id and active:
            return filing_id, client["id"], token, active[0]
    raise AssertionError("포털로 보낼 수 있는 거래처·직원이 없다")


async def _employee_entries(http, headers, filing_id, client_id, employee_id) -> dict[str, dict]:
    entries = (await http.get(f"/api/v1/filings/{filing_id}/entries", headers=headers)).json()
    return {e["id"]: e for e in entries if e["client_id"] == client_id and e["employee_id"] == employee_id}


@pytest.mark.asyncio
async def test_portal_submission_is_recorded_as_owner_not_a_staff_user(http: AsyncClient, auth_headers: dict):
    filing_id, client_id, token, employee_id = await _portal_employee(http, auth_headers)
    before = await _employee_entries(http, auth_headers, filing_id, client_id, employee_id)
    sent = 4_321_000
    touched = None
    try:
        r = await http.post(f"/api/v1/public/r/{token}/submit-amounts",
                            json={"items": [{"employee_id": employee_id, "total_amount": sent}]})
        assert r.status_code == 200, r.text

        after = await _employee_entries(http, auth_headers, filing_id, client_id, employee_id)
        touched = next(e for e in after.values() if e["total_amount"] == sent)  # 방금 보낸 금액의 항목
        rows = await _changes(http, auth_headers, filing_id, touched["id"])
        portal = [c for c in rows if c["source"] == "portal"]
        assert portal, f"포털 이력이 없다: {[(c['action'], c['source']) for c in rows]}"
        assert portal[0]["actor_label"] == "사장님(포털)"  # 직원 계정이 아니라 사장님으로 표기된다
        assert portal[0]["action"] in ("CREATE", "UPDATE")
        row = await _db_entry(touched["id"])
        assert row.source_snapshot["source"] == "portal"
        assert row.source_snapshot["values"]["total_amount"] == sent
    finally:
        if touched is not None:
            if touched["id"] in before:  # 기존 항목을 갱신했다면 값을 되돌린다
                await http.patch(f"/api/v1/filings/{filing_id}/entries/{touched['id']}", headers=auth_headers,
                                 json={"total_amount": before[touched["id"]]["total_amount"],
                                       "approved": before[touched["id"]]["approved"], "edit_reason": "테스트 원복"})
            else:  # 새로 생긴 항목이면 지운다
                await _purge(touched["id"])
