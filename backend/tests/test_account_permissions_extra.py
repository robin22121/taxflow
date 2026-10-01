"""plan/14-accounts-permissions.md 미완료 항목 회귀 테스트.

- 비활성화 즉시 401 (§6.3): JWT가 아직 유효해도 is_active=False면 바로 차단.
- 카카오 미분류함 OWNER 전용화 (§5.3): STAFF는 403, OWNER만 조회·삭제.

시드 관리자 계정("admin@example.com")은 직원계정 기능 이전에 만들어진 레거시라
office.business_number가 비어 있어 직원계정 로그인(email=business_number)이 안 된다.
그래서 매 테스트마다 /register로 새 사무소를 만들어 쓴다.
"""

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import KakaoPendingMessage


async def _register_office(http, business_number: str) -> dict:
    res = await http.post(
        "/api/v1/auth/register",
        json={
            "business_number": business_number,
            "password": "owner!1234",
            "office_name": f"테스트사무소-{business_number}",
            "address": "서울시 종로구 1",
            "representative": "대표자",
            "phone": "01000000000",
            "email": f"office-{business_number}@example.com",
        },
    )
    assert res.status_code == 200, res.text

    login = await http.post(
        "/api/v1/auth/login",
        json={"email": business_number, "password": "owner!1234"},
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _create_staff(http, owner_headers: dict, business_number: str) -> dict:
    create = await http.post(
        "/api/v1/staff",
        json={"name": "직원계정테스트", "password": "staff!1234"},
        headers=owner_headers,
    )
    assert create.status_code == 201, create.text
    staff = create.json()

    login = await http.post(
        "/api/v1/auth/login",
        json={
            "email": business_number,
            "login_code": staff["login_code"],
            "password": "staff!1234",
        },
    )
    assert login.status_code == 200, login.text
    staff["headers"] = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return staff


@pytest.mark.asyncio
async def test_deactivated_staff_gets_401_immediately(http):
    owner_headers = await _register_office(http, "2220001001")
    staff = await _create_staff(http, owner_headers, "2220001001")

    me = await http.get("/api/v1/auth/me", headers=staff["headers"])
    assert me.status_code == 200, me.text

    deactivate = await http.patch(
        f"/api/v1/staff/{staff['id']}",
        json={"is_active": False},
        headers=owner_headers,
    )
    assert deactivate.status_code == 200, deactivate.text

    blocked = await http.get("/api/v1/auth/me", headers=staff["headers"])
    assert blocked.status_code == 401, blocked.text


@pytest.mark.asyncio
async def test_kakao_inbox_owner_only(http):
    owner_headers = await _register_office(http, "2220001002")
    staff = await _create_staff(http, owner_headers, "2220001002")

    owner_me = await http.get("/api/v1/auth/me", headers=owner_headers)
    tax_office_id = owner_me.json()["tax_office_id"]

    async with SessionLocal() as db:
        db.add(
            KakaoPendingMessage(
                plusfriend_key="test-plusfriend-key",
                tax_office_id=tax_office_id,
                utterance="거래처명 없이 온 메시지",
            )
        )
        await db.commit()

    staff_view = await http.get("/api/v1/kakao-inbox", headers=staff["headers"])
    assert staff_view.status_code == 403, staff_view.text

    owner_view = await http.get("/api/v1/kakao-inbox", headers=owner_headers)
    assert owner_view.status_code == 200, owner_view.text
    rows = owner_view.json()
    assert any(r["plusfriend_key"] == "test-plusfriend-key" for r in rows)
    target = next(r for r in rows if r["plusfriend_key"] == "test-plusfriend-key")

    staff_delete = await http.delete(f"/api/v1/kakao-inbox/{target['id']}", headers=staff["headers"])
    assert staff_delete.status_code == 403, staff_delete.text

    owner_delete = await http.delete(f"/api/v1/kakao-inbox/{target['id']}", headers=owner_headers)
    assert owner_delete.status_code == 204, owner_delete.text

    async with SessionLocal() as db:
        remaining = (
            await db.execute(
                select(KakaoPendingMessage).where(KakaoPendingMessage.id == target["id"])
            )
        ).scalar_one_or_none()
        assert remaining is None
