"""위하고 전체 수임처 가져오기 작업 등록 — 최초 도입 시 서버 관리자가 터미널에서 실행한다.

웹의 [전체 가져오기] 버튼과 같은 작업을 만든다. 이 스크립트는 작업을 등록만 하고, 실제 가져오기는
이지원(자동화 노트북)의 에이전트가 작업을 받아 수행한다 — 에이전트(`easyone_agent run`)가 켜져 있어야 시작된다.
수임처 수에 따라 수십 분~수 시간 걸리고, 그동안 에이전트는 다른 작업을 하지 않으므로 업무 시간 외 실행을 권장한다.

실행:
    cd backend && uv run python -m app.scripts.import_wehago_all --office <사무소코드|사업자번호>
    # --admin <로그인ID>  작업 요청자(기본: 사무소 관리자 중 첫 계정)
    # --dry-run           등록하지 않고 대상만 확인
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys

from sqlalchemy import select

from app.api.rpa_import import ALL_IMPORT_NAME, _active_imports
from app.db import SessionLocal
from app.models import RpaJob, RpaJobKind, RpaJobStatus, TaxOffice, User


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="import_wehago_all", description=__doc__.split("\n")[0])
    parser.add_argument("--office", required=True, help="사무소 코드(short_code) 또는 사업자번호")
    parser.add_argument("--admin", help="작업 요청자 로그인 ID (기본: 사무소 관리자 중 첫 계정)")
    parser.add_argument("--dry-run", action="store_true", help="등록하지 않고 대상만 확인")
    args = parser.parse_args(argv)

    digits = re.sub(r"\D", "", args.office)
    async with SessionLocal() as db:
        offices = list(
            (
                await db.execute(
                    select(TaxOffice).where(
                        (TaxOffice.short_code == args.office)
                        | (TaxOffice.business_number == args.office)
                        | (TaxOffice.business_number == digits)
                    )
                )
            ).scalars()
        )
        if len(offices) != 1:
            print(f"사무소를 하나로 특정하지 못했습니다 (찾은 수 {len(offices)}): {args.office}", file=sys.stderr)
            return 1
        office = offices[0]

        admins = list(
            (
                await db.execute(
                    select(User).where(User.tax_office_id == office.id, User.is_admin.is_(True))
                )
            ).scalars()
        )
        admin = next((u for u in admins if u.email == args.admin), None) if args.admin else (admins[0] if admins else None)
        if admin is None:
            print("작업을 요청할 사무소 관리자 계정이 없습니다 (--admin 으로 로그인 ID 지정).", file=sys.stderr)
            return 1

        if any(j.kind == RpaJobKind.WEHAGO_MASTER_IMPORT_ALL for j in await _active_imports(db, office.id)):
            print("위하고 전체 가져오기가 이미 대기·진행 중입니다.", file=sys.stderr)
            return 1

        print(f"대상 사무소: {office.name} ({office.short_code}) / 요청자: {admin.email}")
        if args.dry_run:
            print("[dry-run] 작업을 등록하지 않았습니다.")
            return 0

        job = RpaJob(
            tax_office_id=office.id,
            kind=RpaJobKind.WEHAGO_MASTER_IMPORT_ALL,
            status=RpaJobStatus.PENDING,
            business_name=ALL_IMPORT_NAME,
            requested_by_user_id=admin.id,
        )
        db.add(job)
        await db.commit()
        print(f"전체 가져오기 작업을 등록했습니다 (job {job.id}). 이지원 에이전트가 받아 시작합니다.")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
