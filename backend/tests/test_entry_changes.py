"""급여 항목 변경이력 — 수정·삭제·복구·승인 기록과 조회, 삭제 행 기본 제외."""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient


async def _pick_entry(http: AsyncClient, headers: dict) -> tuple[str, dict]:
    """시드된 신고 건에서 근로소득 항목 하나 (삭제되지 않은 것)."""
    for filing in (await http.get("/api/v1/filings", headers=headers)).json():
        entries = (await http.get(f"/api/v1/filings/{filing['id']}/entries", headers=headers)).json()
        for entry in entries:
            if entry["income_type"] == "WAGE" and entry["total_amount"] > 0:
                return filing["id"], entry
    raise AssertionError("시드에 근로소득 항목이 없다")


async def _changes(http: AsyncClient, headers: dict, filing_id: str, entry_id: str, **params) -> list[dict]:
    r = await http.get(f"/api/v1/filings/{filing_id}/entry-changes",
                       params={"entry_id": entry_id, **params}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _restore_state(http, headers, filing_id, entry):
    """다른 테스트에 영향이 없도록 항목을 처음 상태로 되돌린다."""
    await http.patch(
        f"/api/v1/filings/{filing_id}/entries/{entry['id']}", headers=headers,
        json={"total_amount": entry["total_amount"], "approved": entry["approved"], "deleted": False,
              "edit_reason": "테스트 원복"},
    )


@pytest.mark.asyncio
async def test_value_edit_is_recorded_with_before_after_reason_and_auto_flag(http: AsyncClient, auth_headers: dict):
    filing_id, entry = await _pick_entry(http, auth_headers)
    try:
        new_total = entry["total_amount"] + 100_000
        r = await http.patch(
            f"/api/v1/filings/{filing_id}/entries/{entry['id']}", headers=auth_headers,
            params={"batch_id": "batch-abc"},
            json={"total_amount": new_total, "edit_reason": "금액 정정"},
        )
        assert r.status_code == 200, r.text

        rows = await _changes(http, auth_headers, filing_id, entry["id"])
        update = next(c for c in rows if c["action"] == "UPDATE" and c["reason"] == "금액 정정")
        total = update["changes"]["total_amount"]
        assert total["before"] == entry["total_amount"] and total["after"] == new_total
        assert "auto" not in total  # 직접 고친 값
        assert update["changes"]["taxable"].get("auto") is True  # 자동 재계산된 값
        assert update["actor_label"] and update["source"] == "manual" and update["batch_id"] == "batch-abc"
        # 원본 스냅샷이 없던 이전 자료는 첫 수정 직전 값을 "받은 값"으로 보존한다 (이후 수정으로는 안 바뀐다)
        from app.db import SessionLocal
        from app.models import PayrollEntry

        async with SessionLocal() as db:
            row = await db.get(PayrollEntry, entry["id"])
            assert row.source_snapshot is not None
            assert row.source_snapshot["values"]["total_amount"] == entry["total_amount"]
            assert row.total_amount == new_total  # 현재 값은 수정된 값

        # 주민번호·계좌 같은 값은 이력에 들어가지 않는다 (화이트리스트 필드만)
        dumped = json.dumps(update["changes"], ensure_ascii=False).lower()
        assert "rrn" not in dumped and "account" not in dumped
    finally:
        await _restore_state(http, auth_headers, filing_id, entry)


@pytest.mark.asyncio
async def test_approval_is_recorded_but_hidden_by_default(http: AsyncClient, auth_headers: dict):
    filing_id, entry = await _pick_entry(http, auth_headers)
    try:
        flipped = not entry["approved"]
        r = await http.patch(f"/api/v1/filings/{filing_id}/entries/{entry['id']}", headers=auth_headers,
                             json={"approved": flipped})
        assert r.status_code == 200, r.text

        default_actions = {c["action"] for c in await _changes(http, auth_headers, filing_id, entry["id"])}
        assert "APPROVE" not in default_actions and "UNAPPROVE" not in default_actions

        with_approvals = await _changes(http, auth_headers, filing_id, entry["id"], include_approvals="true")
        expected = "APPROVE" if flipped else "UNAPPROVE"
        assert any(c["action"] == expected for c in with_approvals)
    finally:
        await _restore_state(http, auth_headers, filing_id, entry)


@pytest.mark.asyncio
async def test_value_and_approval_in_one_patch_make_two_rows(http: AsyncClient, auth_headers: dict):
    filing_id, entry = await _pick_entry(http, auth_headers)
    try:
        r = await http.patch(
            f"/api/v1/filings/{filing_id}/entries/{entry['id']}", headers=auth_headers,
            params={"batch_id": "b-two-rows"},
            json={"total_amount": entry["total_amount"] + 5_000, "approved": not entry["approved"],
                  "edit_reason": "동시 변경"},
        )
        assert r.status_code == 200, r.text
        rows = await _changes(http, auth_headers, filing_id, entry["id"], include_approvals="true")
        mine = [c for c in rows if c["batch_id"] == "b-two-rows"]  # 이번 PATCH가 남긴 행만
        approve = "UNAPPROVE" if entry["approved"] else "APPROVE"
        assert sorted(c["action"] for c in mine) == sorted(["UPDATE", approve])
    finally:
        await _restore_state(http, auth_headers, filing_id, entry)


@pytest.mark.asyncio
async def test_delete_hides_entry_and_history_allows_restore(http: AsyncClient, auth_headers: dict):
    filing_id, entry = await _pick_entry(http, auth_headers)
    url = f"/api/v1/filings/{filing_id}/entries/{entry['id']}"
    try:
        r = await http.delete(url, params={"reason": "중복 입력", "batch_id": "b-del"}, headers=auth_headers)
        assert r.status_code == 204, r.text

        # 기본 목록에서는 사라지고, include_deleted 로만 보인다
        visible = (await http.get(f"/api/v1/filings/{filing_id}/entries", headers=auth_headers)).json()
        assert all(e["id"] != entry["id"] for e in visible)
        everything = (await http.get(f"/api/v1/filings/{filing_id}/entries",
                                     params={"include_deleted": "true"}, headers=auth_headers)).json()
        assert next(e for e in everything if e["id"] == entry["id"])["deleted"] is True

        rows = await _changes(http, auth_headers, filing_id, entry["id"])
        delete = next(c for c in rows if c["action"] == "DELETE")
        assert delete["reason"] == "중복 입력" and delete["batch_id"] == "b-del"
        assert delete["changes"]["snapshot"]["total_amount"] == entry["total_amount"]  # 지운 값이 남는다
        assert delete["entry_deleted"] is True  # 패널에서 [복구]를 보여줄 수 있다

        # 다시 삭제해도 이력이 늘지 않는다
        await http.delete(url, headers=auth_headers)
        again = await _changes(http, auth_headers, filing_id, entry["id"])
        assert sum(1 for c in again if c["action"] == "DELETE") == 1

        # 복구
        r = await http.patch(url, json={"deleted": False}, headers=auth_headers)
        assert r.status_code == 200, r.text
        restored = await _changes(http, auth_headers, filing_id, entry["id"])
        assert any(c["action"] == "RESTORE" for c in restored)
        visible = (await http.get(f"/api/v1/filings/{filing_id}/entries", headers=auth_headers)).json()
        assert any(e["id"] == entry["id"] for e in visible)
    finally:
        await _restore_state(http, auth_headers, filing_id, entry)


@pytest.mark.asyncio
async def test_changes_are_scoped_to_visible_clients(http: AsyncClient, auth_headers: dict):
    """담당 거래처가 없는 STAFF는 다른 거래처의 이력을 볼 수 없다."""
    from sqlalchemy import delete, select

    from app.core.security import hash_password
    from app.db import SessionLocal
    from app.models import User

    filing_id, entry = await _pick_entry(http, auth_headers)
    email, pw = "scoped-staff@example.com", "scoped-pw-1234!"
    async with SessionLocal() as db:
        admin = (await db.execute(select(User).where(User.email == "admin@example.com"))).scalar_one()
        db.add(User(tax_office_id=admin.tax_office_id, email=email, password_hash=hash_password(pw),
                    name="담당없음", role="STAFF", can_write=True))
        await db.commit()
    try:
        await http.patch(f"/api/v1/filings/{filing_id}/entries/{entry['id']}", headers=auth_headers,
                         json={"total_amount": entry["total_amount"] + 1, "edit_reason": "스코프 확인"})
        login = await http.post("/api/v1/auth/login", json={"email": email, "password": pw})
        staff = {"Authorization": f"Bearer {login.json()['access_token']}"}

        assert await _changes(http, staff, filing_id, entry["id"]) == []  # 담당 거래처 아님
        assert len(await _changes(http, auth_headers, filing_id, entry["id"])) >= 1  # OWNER는 본다
    finally:
        await _restore_state(http, auth_headers, filing_id, entry)
        async with SessionLocal() as db:
            await db.execute(delete(User).where(User.email == email))
            await db.commit()
