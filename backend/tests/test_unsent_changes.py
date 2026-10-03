"""위하고 전송 이후 재수정 경고 — GET /rpa/unsent-changes (상태를 저장하지 않고 이력과 전송 시각을 비교해 계산)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select

URL = "/api/v1/rpa/unsent-changes"


async def _pick_entry(http: AsyncClient, headers: dict) -> tuple[str, dict]:
    for filing in (await http.get("/api/v1/filings", headers=headers)).json():
        entries = (await http.get(f"/api/v1/filings/{filing['id']}/entries", headers=headers)).json()
        for entry in entries:
            if entry["income_type"] == "WAGE" and entry["total_amount"] > 0:
                return filing["id"], entry
    raise AssertionError("시드에 근로소득 항목이 없다")


async def _add_job(filing_id: str, client_id: str, kind: str, finished_at: datetime) -> str:
    from app.db import SessionLocal
    from app.models import RpaJob, RpaJobKind, RpaJobStatus, User

    async with SessionLocal() as db:
        admin = (await db.execute(select(User).where(User.email == "admin@example.com"))).scalar_one()
        job = RpaJob(
            tax_office_id=admin.tax_office_id, kind=RpaJobKind(kind), status=RpaJobStatus.SUCCEEDED,
            monthly_filing_id=filing_id, client_id=client_id, business_name="테스트", period=None,
            requested_by_user_id=admin.id, finished_at=finished_at,
        )
        db.add(job)
        await db.commit()
        return job.id


async def _clear_filing_jobs(filing_id: str) -> None:
    """다른 테스트가 같은 신고에 남긴 위하고 작업을 지운다 — 이 테스트의 "보낸 적 없음/소득유형별 전송" 가정을 지키려고."""
    from app.db import SessionLocal
    from app.models import RpaJob

    async with SessionLocal() as db:
        await db.execute(delete(RpaJob).where(RpaJob.monthly_filing_id == filing_id))
        await db.commit()


async def _settle(http, headers, filing_id, entry) -> None:
    """사유만 바꾼 PATCH도 비과세 정규화 같은 자동 보정으로 값을 바꾸는 항목이 있다 — 먼저 한 번 안정시켜 둔다."""
    await http.patch(f"/api/v1/filings/{filing_id}/entries/{entry['id']}", headers=headers,
                     json={"edit_reason": "정리"})


async def _drop_jobs(ids: list[str]) -> None:
    from app.db import SessionLocal
    from app.models import RpaJob

    async with SessionLocal() as db:
        await db.execute(delete(RpaJob).where(RpaJob.id.in_(ids)))
        await db.commit()


async def _unsent(http: AsyncClient, headers: dict, filing_id: str, client_id: str) -> dict | None:
    r = await http.get(URL, params={"filing_id": filing_id}, headers=headers)
    assert r.status_code == 200, r.text
    return next((u for u in r.json() if u["client_id"] == client_id), None)


async def _restore(http, headers, filing_id, entry):
    await http.patch(f"/api/v1/filings/{filing_id}/entries/{entry['id']}", headers=headers,
                     json={"total_amount": entry["total_amount"], "approved": entry["approved"],
                           "deleted": False, "edit_reason": "테스트 원복"})


@pytest.mark.asyncio
async def test_edit_after_send_is_flagged_until_resent(http: AsyncClient, auth_headers: dict):
    filing_id, entry = await _pick_entry(http, auth_headers)
    client_id = entry["client_id"]
    job_ids: list[str] = []
    await _clear_filing_jobs(filing_id)
    await _settle(http, auth_headers, filing_id, entry)
    try:
        # 전송 성공 전에는 경고가 없다 — 보낸 적이 없으니 "재전송"할 것도 없다
        assert await _unsent(http, auth_headers, filing_id, client_id) is None

        # 전송 성공 시각을 "지금"으로 둔다 — 앞선 테스트가 같은 거래처에 남긴 이력은 전부 이보다 이전이다.
        job_ids.append(await _add_job(filing_id, client_id, "WEHAGO_PAYROLL_INPUT", datetime.now(UTC)))
        await asyncio.sleep(0.05)
        assert await _unsent(http, auth_headers, filing_id, client_id) is None  # 보낸 뒤 고친 게 없다

        # 사유만 바꾼 수정은 세지 않는다
        await http.patch(f"/api/v1/filings/{filing_id}/entries/{entry['id']}", headers=auth_headers,
                         json={"edit_reason": "메모만 변경"})
        assert await _unsent(http, auth_headers, filing_id, client_id) is None

        # 값을 고치면 경고
        await http.patch(f"/api/v1/filings/{filing_id}/entries/{entry['id']}", headers=auth_headers,
                         json={"total_amount": entry["total_amount"] + 10_000, "edit_reason": "금액 정정"})
        flagged = await _unsent(http, auth_headers, filing_id, client_id)
        assert flagged and flagged["income_types"] == ["WAGE"] and flagged["count"] >= 1
        assert flagged["after"] == "input"

        # 삭제도 미전송 수정이다
        await http.delete(f"/api/v1/filings/{filing_id}/entries/{entry['id']}", headers=auth_headers)
        assert (await _unsent(http, auth_headers, filing_id, client_id))["count"] >= 2

        # 재전송이 성공하면 경고가 사라진다
        job_ids.append(await _add_job(filing_id, client_id, "WEHAGO_PAYROLL_INPUT",
                                      datetime.now(UTC) + timedelta(seconds=30)))
        assert await _unsent(http, auth_headers, filing_id, client_id) is None
    finally:
        await _restore(http, auth_headers, filing_id, entry)
        await _drop_jobs(job_ids)


@pytest.mark.asyncio
async def test_edit_after_production_is_flagged_as_stronger_and_other_types_are_independent(
    http: AsyncClient, auth_headers: dict
):
    filing_id, entry = await _pick_entry(http, auth_headers)
    client_id = entry["client_id"]
    job_ids: list[str] = []
    await _clear_filing_jobs(filing_id)
    await _settle(http, auth_headers, filing_id, entry)
    try:
        job_ids.append(await _add_job(filing_id, client_id, "WEHAGO_PAYROLL_INPUT", datetime.now(UTC)))
        await asyncio.sleep(0.05)
        job_ids.append(await _add_job(filing_id, client_id, "MONTHLY_PRODUCTION", datetime.now(UTC)))
        await asyncio.sleep(0.05)
        await http.patch(f"/api/v1/filings/{filing_id}/entries/{entry['id']}", headers=auth_headers,
                         json={"total_amount": entry["total_amount"] + 7_000, "edit_reason": "제작 후 정정"})
        flagged = await _unsent(http, auth_headers, filing_id, client_id)
        assert flagged and flagged["after"] == "production"  # 제작까지 끝난 뒤에 고쳤다

        # 근로 전송 기록만 있으면 사업소득 항목의 수정은 이 경고 대상이 아니다 (소득유형별로 독립)
        from app.db import SessionLocal
        from app.models import RpaJob

        async with SessionLocal() as db:
            await db.execute(delete(RpaJob).where(RpaJob.id.in_(job_ids[:1])))
            await db.commit()
        job_ids[0] = await _add_job(filing_id, client_id, "WEHAGO_BUSINESS_INPUT", datetime.now(UTC))
        assert await _unsent(http, auth_headers, filing_id, client_id) is None  # 근로 수정 vs 사업 전송
    finally:
        await _restore(http, auth_headers, filing_id, entry)
        await _drop_jobs(job_ids)


@pytest.mark.asyncio
async def test_unsent_changes_requires_own_filing(http: AsyncClient, auth_headers: dict):
    r = await http.get(URL, params={"filing_id": "no-such-filing"}, headers=auth_headers)
    assert r.status_code == 404
