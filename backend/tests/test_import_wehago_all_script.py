"""위하고 전체 가져오기 터미널 스크립트 — 작업 등록·중복 방지·dry-run."""

from __future__ import annotations

import pytest
from sqlalchemy import select, update


async def _office_short_code() -> str:
    from app.db import SessionLocal
    from app.models import TaxOffice, User

    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == "admin@example.com"))).scalar_one()
        office = await db.get(TaxOffice, user.tax_office_id)
        if not office.short_code:
            office.short_code = "SCRIPT01"
            await db.commit()
        return office.short_code


async def _master_jobs() -> list:
    from app.db import SessionLocal
    from app.models import RpaJob, RpaJobKind

    async with SessionLocal() as db:
        rows = await db.execute(select(RpaJob).where(RpaJob.kind == RpaJobKind.WEHAGO_MASTER_IMPORT_ALL))
        return list(rows.scalars())


async def _cancel_active() -> None:
    from app.db import SessionLocal
    from app.models import RpaJob, RpaJobStatus

    async with SessionLocal() as db:
        await db.execute(
            update(RpaJob)
            .where(RpaJob.status.in_([RpaJobStatus.PENDING, RpaJobStatus.RUNNING]))
            .values(status=RpaJobStatus.CANCELED)
        )
        await db.commit()


@pytest.mark.asyncio
async def test_script_enqueues_master_import_once(http, auth_headers, capsys):
    from app.models import RpaJobKind, RpaJobStatus
    from app.scripts.import_wehago_all import main

    await _cancel_active()
    code = await _office_short_code()
    before = len(await _master_jobs())

    # dry-run — 등록하지 않는다
    assert await main(["--office", code, "--dry-run"]) == 0
    assert len(await _master_jobs()) == before

    # 실제 등록
    assert await main(["--office", code, "--admin", "admin@example.com"]) == 0
    jobs = await _master_jobs()
    assert len(jobs) == before + 1
    job = jobs[-1]
    assert job.kind == RpaJobKind.WEHAGO_MASTER_IMPORT_ALL and job.status == RpaJobStatus.PENDING

    # 이미 대기·진행 중이면 두 번째는 거절
    assert await main(["--office", code]) == 1
    assert "이미 대기·진행 중" in capsys.readouterr().err
    assert len(await _master_jobs()) == before + 1

    await _cancel_active()


@pytest.mark.asyncio
async def test_script_rejects_unknown_office_and_non_admin(http, auth_headers, capsys):
    from app.scripts.import_wehago_all import main

    assert await main(["--office", "NOPE9999"]) == 1
    assert "특정하지 못했습니다" in capsys.readouterr().err

    code = await _office_short_code()
    assert await main(["--office", code, "--admin", "nobody@example.com"]) == 1
    assert "관리자 계정이 없습니다" in capsys.readouterr().err
