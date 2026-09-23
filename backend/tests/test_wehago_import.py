"""위하고 → 이지원천 임포트 — 수임처·사원 기본사항 반영 규칙과 작업 흐름 (plan/16 §12)."""

from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

CLAIM = "/api/v1/rpa/agent/claim"


async def _clear_active_jobs() -> None:
    """세션 공용 DB라 다른 테스트가 남긴 대기·진행 작업이 claim 순서를 흔든다."""
    from app.db import SessionLocal
    from app.models import RpaJob, RpaJobStatus

    async with SessionLocal() as db:
        await db.execute(
            update(RpaJob)
            .where(RpaJob.status.in_([RpaJobStatus.PENDING, RpaJobStatus.RUNNING]))
            .values(status=RpaJobStatus.CANCELED)
        )
        await db.commit()


async def _office_id() -> str:
    from app.db import SessionLocal
    from app.models import User

    async with SessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == "admin@example.com"))
        ).scalar_one()
        return user.tax_office_id


async def _agent(http: AsyncClient, auth_headers: dict) -> dict[str, str]:
    r = await http.post("/api/v1/rpa/agents", json={"name": "임포트 PC"}, headers=auth_headers)
    assert r.status_code == 201, r.text
    return {"X-Agent-Token": r.json()["token"]}


# --- 반영 규칙 (서비스) ------------------------------------------------------


@pytest.mark.asyncio
async def test_new_client_and_employees_are_created_with_encrypted_rrn():
    from app.db import SessionLocal
    from app.models import Employee
    from app.services.crypto import decrypt_rrn
    from app.services.wehago_import import ImportedClient, ImportedEmployee, apply_client_import

    office_id = await _office_id()
    async with SessionLocal() as db:
        out = await apply_client_import(
            db,
            office_id,
            ImportedClient(
                business_number="2240238401",
                business_name="임포트신규상사",
                representative="엄순덕",
                business_type="부동산업",
                employees=[
                    ImportedEmployee("1", "한지민", rrn="600915-2000001", hired_at=date(2020, 1, 1)),
                    ImportedEmployee("2", "오세훈", resigned_at=date(2026, 1, 31)),
                ],
            ),
            today=date(2026, 9, 23),
        )
        await db.commit()

        assert out.client_created and out.employees_created == 2 and not out.conflicts
        assert out.client.business_number == "224-02-38401"
        emps = {
            e.name: e
            for e in (
                await db.execute(select(Employee).where(Employee.client_id == out.client.id))
            ).scalars()
        }
        assert emps["한지민"].employee_code == "1"
        assert decrypt_rrn(emps["한지민"].rrn_encrypted) == "6009152000001"
        assert emps["한지민"].rrn_last4 == "0001"
        assert emps["오세훈"].status.value == "RESIGNED"


@pytest.mark.asyncio
async def test_existing_values_are_kept_and_differences_reported():
    """빈 칸만 채우고, 다른 값은 덮지 않고 차이로 돌려준다. 사원코드만 위하고 값으로 맞춘다."""
    from app.db import SessionLocal
    from app.models import Client, Employee
    from app.services.crypto import encrypt_rrn
    from app.services.wehago_import import ImportedClient, ImportedEmployee, apply_client_import

    office_id = await _office_id()
    async with SessionLocal() as db:
        client = Client(tax_office_id=office_id, business_name="기존상사",
                        business_number="224-02-38402", representative="김대표")
        db.add(client)
        await db.flush()
        by_rrn = Employee(client_id=client.id, name="윤미래", employee_code="7",
                          rrn_encrypted=encrypt_rrn("8306262000003"), department="총무부")
        by_name = Employee(client_id=client.id, name="서유나")  # 사원코드 없음
        db.add_all([by_rrn, by_name])
        await db.commit()

        out = await apply_client_import(
            db,
            office_id,
            ImportedClient(
                business_number="224-02-38402",
                business_name="기존상사",
                representative="이대표",  # 다름 → 덮지 않음
                business_address="서울시 어딘가",  # 빈 칸 → 채움
                employees=[
                    ImportedEmployee("3", "윤미래", rrn="830626-2000003", department="영업부"),
                    ImportedEmployee("4", "서유나", position="대리"),
                ],
            ),
        )
        await db.commit()

        assert not out.client_created
        assert out.client.representative == "김대표"
        assert out.client.business_address == "서울시 어딘가"
        assert by_rrn.employee_code == "3"  # 주민번호로 찾아 위하고 코드로 맞춤
        assert by_rrn.department == "총무부"
        assert by_name.employee_code == "4" and by_name.position == "대리"  # 이름으로 찾아 채움
        assert out.employees_created == 0 and out.employees_updated == 2
        fields = {(c["target"], c["field"]) for c in out.conflicts}
        assert fields == {("수임처", "대표자"), ("윤미래", "사원코드(위하고 값으로 변경)"),
                          ("윤미래", "부서")}


# --- 작업 흐름 (API) ---------------------------------------------------------


@pytest.mark.asyncio
async def test_client_import_job_flow(http: AsyncClient, auth_headers: dict):
    await _clear_active_jobs()
    agent = await _agent(http, auth_headers)

    r = await http.post("/api/v1/rpa/imports/clients",
                        json={"business_number": "224-02-38403"}, headers=auth_headers)
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["kind"] == "WEHAGO_CLIENT_IMPORT" and job["client_id"] is None

    dup = await http.post("/api/v1/rpa/imports/clients",
                          json={"business_number": "2240238403"}, headers=auth_headers)
    assert dup.status_code == 409

    claimed = (await http.post(CLAIM, headers=agent)).json()["job"]
    assert claimed["id"] == job["id"] and claimed["business_number"] == "224-02-38403"

    url = f"/api/v1/rpa/agent/imports/{job['id']}/client-result"
    wrong = await http.post(url, json={"business_number": "1112233333", "business_name": "딴회사"},
                            headers=agent)
    assert wrong.status_code == 409

    res = await http.post(url, headers=agent, json={
        "business_number": "224-02-38403",
        "business_name": "서도",
        "representative": "엄순덕",
        "employees": [{"employee_code": "1", "name": "한지민", "rrn": "600915-2000001",
                       "hired_at": "2020-01-01"}],
    })
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["client_created"] and body["employees_created"] == 1

    done = await http.post(f"/api/v1/rpa/agent/jobs/{job['id']}/result", headers=agent,
                           json={"status": "SUCCEEDED", "message": "수임처 1건"})
    assert done.status_code == 200, done.text

    listed = (await http.get("/api/v1/rpa/imports", headers=auth_headers)).json()
    mine = next(j for j in listed if j["id"] == job["id"])
    assert mine["client_id"] == body["client_id"] and mine["business_name"] == "서도"
    entry = mine["step_progress"]["clients"][0]
    assert entry["status"] == "SUCCEEDED" and "rrn" not in str(entry)

    notes = (await http.get("/api/v1/rpa/notifications", headers=auth_headers)).json()
    assert any(n["kind"] == "IMPORT_DONE" and n["job_id"] == job["id"] for n in notes)


@pytest.mark.asyncio
async def test_master_import_records_progress_per_client(http: AsyncClient, auth_headers: dict):
    await _clear_active_jobs()
    agent = await _agent(http, auth_headers)

    r = await http.post("/api/v1/rpa/imports/master-all", headers=auth_headers)
    assert r.status_code == 201, r.text
    job = r.json()
    assert (await http.post("/api/v1/rpa/imports/master-all", headers=auth_headers)).status_code == 409
    # 전체 가져오기 중에는 개별 가져오기를 받지 않는다 (같은 위하고 계정을 쓰므로)
    blocked = await http.post("/api/v1/rpa/imports/clients",
                              json={"business_number": "2240238404"}, headers=auth_headers)
    assert blocked.status_code == 409

    assert (await http.post(CLAIM, headers=agent)).json()["job"]["id"] == job["id"]
    url = f"/api/v1/rpa/agent/imports/{job['id']}/client-result"
    ok = await http.post(url, headers=agent, json={
        "business_number": "2240238404", "business_name": "전체1", "total": 2, "employees": []})
    assert ok.status_code == 200, ok.text
    failed = await http.post(url, headers=agent, json={
        "business_number": "2240238405", "business_name": "전체2", "total": 2,
        "error": "사원등록 화면을 열지 못함"})
    assert failed.status_code == 200, failed.text

    listed = (await http.get("/api/v1/rpa/imports", headers=auth_headers)).json()
    progress = next(j for j in listed if j["id"] == job["id"])["step_progress"]
    assert progress["total"] == 2
    assert [c["status"] for c in progress["clients"]] == ["SUCCEEDED", "FAILED"]
