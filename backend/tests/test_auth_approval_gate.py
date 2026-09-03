"""임시 검증 — 승인 대기 상태에서도 로그인이 되는지 확인."""

import pytest


@pytest.mark.asyncio
async def test_pending_office_can_login(http):
    payload = {
        "business_number": "1112233445",
        "password": "test!1234",
        "office_name": "테스트세무회계",
        "address": "서울시 종로구 1",
        "representative": "홍길동",
        "phone": "01012345678",
        "email": "pending@example.com",
    }
    res = await http.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 200, res.text
    assert res.json()["approval_status"] == "PENDING"

    login = await http.post(
        "/api/v1/auth/login",
        json={"email": "1112233445", "password": "test!1234"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["access_token"]
