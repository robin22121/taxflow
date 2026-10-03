"""급여 항목 무결성 — 읽기 전용 직원의 쓰기 차단, 자료 삭제 시 항목이 하드 삭제되지 않음."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select

STAFF_EMAIL = "readonly-staff@example.com"
STAFF_PASSWORD = "readonly-pw-1234!"


@pytest_asyncio.fixture
async def readonly_headers(http: AsyncClient):
    """can_write=False 인 STAFF 계정 (plan/14 §3.2)."""
    from app.core.security import hash_password
    from app.db import SessionLocal
    from app.models import User

    async with SessionLocal() as db:
        admin = (await db.execute(select(User).where(User.email == "admin@example.com"))).scalar_one()
        db.add(
            User(
                tax_office_id=admin.tax_office_id,
                email=STAFF_EMAIL,
                password_hash=hash_password(STAFF_PASSWORD),
                name="읽기전용",
                role="STAFF",
                can_write=False,
            )
        )
        await db.commit()

    r = await http.post("/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD})
    assert r.status_code == 200, r.text
    yield {"Authorization": f"Bearer {r.json()['access_token']}"}

    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.email == STAFF_EMAIL))
        await db.commit()


@pytest.mark.asyncio
async def test_readonly_staff_cannot_use_collect_or_fast_path_writes(
    http: AsyncClient, readonly_headers: dict, auth_headers: dict
):
    """수집·페스트패스의 쓰기 라우트는 읽기 전용 STAFF에게 403 — 예전에는 막는 장치가 없었다."""
    sid = "no-such-session"
    writes = [
        ("post", f"/api/v1/collect/sessions/{sid}/messages",
         {"json": {"text": "홍길동 300만원", "sender_name": "사장님", "received_date": "2026-10-01"}}),
        ("post", f"/api/v1/collect/sessions/{sid}/messages/commit", {"json": {}}),
        ("post", f"/api/v1/collect/sessions/{sid}/text/preview", {"json": {"text": "홍길동 300만원"}}),
        ("post", f"/api/v1/collect/sessions/{sid}/upload/preview",
         {"files": {"file": ("a.txt", b"hello", "text/plain")}}),
        ("post", "/api/v1/filings/no-filing/clients/no-client/fast-path/commit", {"json": {}}),
    ]
    for method, url, kwargs in writes:
        r = await getattr(http, method)(url, headers=readonly_headers, **kwargs)
        assert r.status_code == 403, (url, r.status_code, r.text)

    # 대조군 — 쓰기 가능한 계정은 권한 검사를 통과해 (존재하지 않는 세션이라) 404를 받는다.
    r = await http.post(
        f"/api/v1/collect/sessions/{sid}/text/preview", headers=auth_headers, json={"text": "홍길동 300만원"}
    )
    assert r.status_code == 404, r.text


async def _session_with_events():
    """시드된 세션 하나에 텍스트 이벤트+첨부 이벤트와 각각의 급여 항목을 추가한다 (정리는 id 기준)."""
    from app.db import SessionLocal
    from app.models import CollectionEvent, CollectionSession, PayrollEntry

    async with SessionLocal() as db:
        session = (await db.execute(select(CollectionSession).limit(1))).scalar_one()

        text_ev = CollectionEvent(session_id=session.id, event_type="RECEIVE_KAKAO", raw_text="김텍스트 200만원",
                                  raw_payload={})
        file_ev = CollectionEvent(
            session_id=session.id, event_type="RECEIVE_EXCEL", raw_text=None,
            raw_payload={"attachments": [{"storage_key": "k-int-1", "filename": "a.xlsx"}]},
        )
        db.add_all([text_ev, file_ev])
        await db.flush()

        common = dict(monthly_filing_id=session.monthly_filing_id, collection_session_id=session.id,
                      client_id=session.client_id)
        text_entry = PayrollEntry(collection_event_id=text_ev.id, raw_name="김텍스트", total_amount=2_000_000, **common)
        file_entry = PayrollEntry(collection_event_id=file_ev.id, raw_name="이파일", total_amount=3_000_000, **common)
        db.add_all([text_entry, file_entry])
        await db.commit()
        return {
            "filing_id": session.monthly_filing_id, "session_id": session.id,
            "text_event_id": text_ev.id, "file_event_id": file_ev.id,
            "text_entry_id": text_entry.id, "file_entry_id": file_entry.id,
        }


async def _cleanup(ids: dict):
    from app.db import SessionLocal
    from app.models import CollectionEvent, PayrollEntry

    entry_ids = [ids["text_entry_id"], ids["file_entry_id"]]
    event_ids = [ids["text_event_id"], ids["file_event_id"]]
    async with SessionLocal() as db:
        await db.execute(delete(PayrollEntry).where(PayrollEntry.id.in_(entry_ids)))
        await db.execute(delete(CollectionEvent).where(CollectionEvent.id.in_(event_ids)))
        await db.commit()


async def _entry(entry_id: str):
    from app.db import SessionLocal
    from app.models import PayrollEntry

    async with SessionLocal() as db:
        return await db.get(PayrollEntry, entry_id)


@pytest.mark.asyncio
async def test_deleting_an_attachment_only_removes_entries_of_that_attachment(http: AsyncClient, auth_headers: dict):
    """첨부 하나를 지워도 같은 세션의 텍스트 입력에서 나온 항목은 그대로 — 예전에는 함께 하드 삭제됐다."""
    ids = await _session_with_events()
    try:
        r = await http.delete(
            f"/api/v1/filings/{ids['filing_id']}/sessions/{ids['session_id']}/attachments",
            params={"key": "k-int-1", "deleted_by": "테스터"}, headers=auth_headers,
        )
        assert r.status_code == 200, r.text

        text_entry = await _entry(ids["text_entry_id"])
        assert text_entry is not None and text_entry.deleted is False  # 텍스트 항목은 건드리지 않는다

        file_entry = await _entry(ids["file_entry_id"])
        assert file_entry is not None and file_entry.deleted is True  # 첨부 항목은 소프트 삭제(행은 남음)
    finally:
        await _cleanup(ids)


@pytest.mark.asyncio
async def test_deleting_an_event_soft_deletes_its_entries(http: AsyncClient, auth_headers: dict):
    """이벤트를 지워도 항목 행은 남고(deleted=True), 이벤트 FK만 끊긴다."""
    ids = await _session_with_events()
    try:
        r = await http.delete(
            f"/api/v1/filings/{ids['filing_id']}/sessions/{ids['session_id']}/events/{ids['text_event_id']}",
            params={"deleted_by": "테스터"}, headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["entries_removed"] == 1

        text_entry = await _entry(ids["text_entry_id"])
        assert text_entry is not None  # 하드 삭제되지 않았다
        assert text_entry.deleted is True and text_entry.collection_event_id is None

        file_entry = await _entry(ids["file_entry_id"])
        assert file_entry.deleted is False  # 다른 이벤트의 항목은 그대로
    finally:
        await _cleanup(ids)
