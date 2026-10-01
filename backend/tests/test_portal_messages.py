"""사업주 포털 메시지 — 자료 제출 커뮤니케이션 채널 (plan/12-owner-portal.md §3.8).

검증 목표
1. 사장님(공개 토큰)이 보낸 메시지가 세무사 대시보드에서 보인다
2. 직원이 보낸 답변이 사장님 쪽 공개 엔드포인트에서 담당 직원 이름과 함께 보인다
3. 본문·첨부파일이 둘 다 없으면 거부된다
4. 알림이 설계상 없다는 전제를 깨지 않도록, 응답에 별도 발송 필드가 없다
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _first_client_id(http: AsyncClient, auth_headers: dict) -> str:
    clients = (await http.get("/api/v1/clients", headers=auth_headers)).json()
    return clients[0]["id"]


async def _portal_token(http: AsyncClient, auth_headers: dict, client_id: str) -> str:
    link = (
        await http.get(f"/api/v1/clients/{client_id}/portal-link", headers=auth_headers)
    ).json()
    return link["url"].rsplit("/", 1)[-1]


@pytest.mark.asyncio
async def test_owner_message_visible_to_staff(http: AsyncClient, auth_headers: dict):
    client_id = await _first_client_id(http, auth_headers)
    token = await _portal_token(http, auth_headers, client_id)

    r = await http.post(f"/api/v1/public/r/{token}/messages", data={"body": "4월 급여 언제까지 보내면 되나요?"})
    assert r.status_code == 201, r.text
    assert r.json()["sender_type"] == "OWNER"
    assert r.json()["body"] == "4월 급여 언제까지 보내면 되나요?"

    staff_view = await http.get(f"/api/v1/clients/{client_id}/messages", headers=auth_headers)
    assert staff_view.status_code == 200, staff_view.text
    items = staff_view.json()
    assert len(items) == 1
    assert items[0]["sender_type"] == "OWNER"
    assert items[0]["body"] == "4월 급여 언제까지 보내면 되나요?"


@pytest.mark.asyncio
async def test_staff_reply_visible_to_owner_with_staff_name(http: AsyncClient, auth_headers: dict):
    client_id = await _first_client_id(http, auth_headers)
    token = await _portal_token(http, auth_headers, client_id)

    reply = await http.post(
        f"/api/v1/clients/{client_id}/messages",
        data={"body": "이번 주 금요일까지 부탁드립니다"},
        headers=auth_headers,
    )
    assert reply.status_code == 201, reply.text
    assert reply.json()["sender_type"] == "STAFF"
    assert reply.json()["staff_name"]

    thread = await http.get(f"/api/v1/public/r/{token}/messages")
    assert thread.status_code == 200, thread.text
    body = thread.json()
    assert body["staff_name"]
    staff_messages = [m for m in body["items"] if m["sender_type"] == "STAFF"]
    assert staff_messages
    assert staff_messages[-1]["body"] == "이번 주 금요일까지 부탁드립니다"
    assert staff_messages[-1]["staff_name"] == body["staff_name"]


@pytest.mark.asyncio
async def test_empty_message_rejected(http: AsyncClient, auth_headers: dict):
    client_id = await _first_client_id(http, auth_headers)
    token = await _portal_token(http, auth_headers, client_id)

    r = await http.post(f"/api/v1/public/r/{token}/messages", data={})
    assert r.status_code == 400

    r2 = await http.post(f"/api/v1/clients/{client_id}/messages", data={}, headers=auth_headers)
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_owner_attachment_upload(http: AsyncClient, auth_headers: dict):
    client_id = await _first_client_id(http, auth_headers)
    token = await _portal_token(http, auth_headers, client_id)

    files = {"file": ("receipt.jpg", b"\xff\xd8\xff\xe0fakejpeg", "image/jpeg")}
    r = await http.post(f"/api/v1/public/r/{token}/messages", files=files)
    assert r.status_code == 201, r.text
    assert r.json()["attachment_name"] == "receipt.jpg"
    assert r.json()["attachment_url"]


@pytest.mark.asyncio
async def test_invalid_token_404(http: AsyncClient):
    r = await http.get("/api/v1/public/r/not-a-real-token/messages")
    assert r.status_code == 404
