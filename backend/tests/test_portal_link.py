"""거래처 상설 링크 — 토큰 해석·발급·무효화 (plan/12-owner-portal.md §4.3, §5.3).

검증 목표 3가지
1. 이미 발송된 구 세션 링크가 계속 동작한다
2. 상설 링크는 항상 "지금 열린 신고"로 해석된다
3. 열린 신고가 없으면 조회는 accepting=False, 제출은 409
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


async def _april_filing(http: AsyncClient, auth_headers: dict) -> dict:
    filings = (await http.get("/api/v1/filings", headers=auth_headers)).json()
    return next(f for f in filings if f["period"] == "2026-04")


async def _first_client_id(http: AsyncClient, auth_headers: dict) -> str:
    clients = (await http.get("/api/v1/clients", headers=auth_headers)).json()
    return clients[0]["id"]


@pytest.mark.asyncio
async def test_legacy_session_link_still_resolves(http: AsyncClient, auth_headers: dict):
    """구 링크(/r/{request_token})는 죽지 않는다 — 이미 발송된 알림톡이 살아 있어야 한다."""
    apr = await _april_filing(http, auth_headers)
    dash = (await http.get(f"/api/v1/filings/{apr['id']}/dashboard", headers=auth_headers)).json()
    token = dash["sessions"][0]["request_token"]

    r = await http.get(f"/api/v1/public/r/{token}")
    assert r.status_code == 200, r.text
    assert r.json()["period"] == "2026-04"
    assert r.json()["accepting"] is True


@pytest.mark.asyncio
async def test_portal_link_resolves_to_current_open_filing(http: AsyncClient, auth_headers: dict):
    """상설 링크는 기간이 박혀 있지 않고 열린 신고(2026-04)로 해석된다."""
    client_id = await _first_client_id(http, auth_headers)
    r = await http.get(f"/api/v1/clients/{client_id}/portal-link", headers=auth_headers)
    assert r.status_code == 200, r.text
    token = r.json()["url"].rsplit("/", 1)[-1]

    pub = await http.get(f"/api/v1/public/r/{token}")
    assert pub.status_code == 200, pub.text
    assert pub.json()["period"] == "2026-04"
    assert pub.json()["accepting"] is True


@pytest.mark.asyncio
async def test_portal_link_is_stable_across_calls(http: AsyncClient, auth_headers: dict):
    """거래처당 활성 토큰은 1개 — 다시 조회해도 같은 URL이어야 재방문이 성립한다."""
    client_id = await _first_client_id(http, auth_headers)
    first = (await http.get(f"/api/v1/clients/{client_id}/portal-link", headers=auth_headers)).json()
    second = (await http.get(f"/api/v1/clients/{client_id}/portal-link", headers=auth_headers)).json()
    assert first["url"] == second["url"]


@pytest.mark.asyncio
async def test_rotate_kills_old_link(http: AsyncClient, auth_headers: dict):
    """재발급하면 옛 링크는 즉시 죽는다 (§4.5 강제 무효화)."""
    clients = (await http.get("/api/v1/clients", headers=auth_headers)).json()
    client_id = clients[1]["id"]
    old = (await http.get(f"/api/v1/clients/{client_id}/portal-link", headers=auth_headers)).json()
    old_token = old["url"].rsplit("/", 1)[-1]
    assert (await http.get(f"/api/v1/public/r/{old_token}")).status_code == 200

    new = (
        await http.post(f"/api/v1/clients/{client_id}/portal-link/rotate", headers=auth_headers)
    ).json()
    new_token = new["url"].rsplit("/", 1)[-1]

    assert new_token != old_token
    assert (await http.get(f"/api/v1/public/r/{old_token}")).status_code == 404
    assert (await http.get(f"/api/v1/public/r/{new_token}")).status_code == 200


@pytest.mark.asyncio
async def test_portal_submit_creates_session_on_open_filing(http: AsyncClient, auth_headers: dict):
    """제출 경로는 열린 신고의 세션을 만들어 붙인다 (AI 파이프라인은 타지 않고 서비스 레벨로 검증)."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Client
    from app.services.portal import get_or_issue_portal_token, resolve_public_link

    apr = await _april_filing(http, auth_headers)

    async with SessionLocal() as db:
        client = (await db.execute(select(Client).order_by(Client.business_name))).scalars().first()
        token = await get_or_issue_portal_token(db, client)
        await db.commit()

        link = await resolve_public_link(db, token.token, create_session=True)
        await db.commit()

    assert link is not None
    assert link.filing.id == apr["id"]
    assert link.session is not None
    assert link.session.monthly_filing_id == apr["id"]
    assert link.session.client_id == client.id


@pytest.mark.asyncio
async def test_no_open_filing_is_not_accepting(http: AsyncClient):
    """열린 신고가 없는 거래처 — 조회는 안내만, 제출은 409로 막는다."""
    from app.db import SessionLocal
    from app.models import Client, TaxOffice
    from app.services.portal import get_or_issue_portal_token

    async with SessionLocal() as db:
        office = TaxOffice(name="신고없는사무소")
        db.add(office)
        await db.flush()
        client = Client(tax_office_id=office.id, business_name="신고없는거래처")
        db.add(client)
        await db.flush()
        token = await get_or_issue_portal_token(db, client)
        await db.commit()
        token_str = token.token

    r = await http.get(f"/api/v1/public/r/{token_str}")
    assert r.status_code == 200, r.text
    assert r.json()["accepting"] is False
    assert r.json()["period"] == ""

    submitted = await http.post(f"/api/v1/public/r/{token_str}/submit", json={"text": "홍길동 300만원"})
    assert submitted.status_code == 409, submitted.text


@pytest.mark.asyncio
async def test_invite_carries_portal_link_not_session_token(
    http: AsyncClient, auth_headers: dict
):
    """발송 경로는 상설 링크를 싣는다 — 세션 토큰이 나가면 달마다 링크가 바뀐다 (§3.6)."""
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import CollectionEvent, CollectionSession

    client_id = await _first_client_id(http, auth_headers)
    link = (
        await http.get(f"/api/v1/clients/{client_id}/portal-link", headers=auth_headers)
    ).json()["url"]

    sent = await http.post(f"/api/v1/clients/{client_id}/invite", headers=auth_headers)
    assert sent.status_code == 200, sent.text

    async with SessionLocal() as db:
        event = (
            await db.execute(
                select(CollectionEvent)
                .join(CollectionSession, CollectionSession.id == CollectionEvent.session_id)
                .where(
                    CollectionSession.client_id == client_id,
                    CollectionEvent.event_type == "SEND_INVITE",
                )
                .order_by(CollectionEvent.created_at.desc())
            )
        ).scalars().first()

    assert event is not None
    assert link in event.raw_text


@pytest.mark.asyncio
async def test_unknown_token_is_404(http: AsyncClient):
    assert (await http.get("/api/v1/public/r/nope-not-a-real-token")).status_code == 404
