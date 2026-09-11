"""발송 본문이 상설 링크를 싣는지 (plan/12-owner-portal.md §3.6, §4.3.1).

세션 토큰 URL을 직접 조립하면 달마다 링크가 바뀌어, 사장님이 옛 알림톡 링크로
옛 기간 폼에 이번 달 자료를 넣는 사고가 난다. 발송 3경로가 모두
``portal_link_for()``를 거치는지 여기서 고정한다.

실제 문자·메일은 나가지 않는다. 채널을 가로채 본문만 확인한다.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.channels import SendResult


class _CaptureChannel:
    """발송 대신 본문을 모아두는 가짜 채널."""

    name = "capture"

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, recipient, *, body: str, url: str | None = None, **kwargs):
        self.sent.append({"body": body, "url": url, "to": recipient})
        return SendResult(channel=self.name, accepted=True, provider_msg_id="captured")

    def bodies(self) -> str:
        return "\n".join(item["body"] for item in self.sent)


async def _client_and_filing(db, *, with_contact: bool):
    from app.models import Client, MonthlyFiling

    client = (
        await db.execute(select(Client).order_by(Client.business_name))
    ).scalars().first()
    if with_contact:
        client.contact_phone = client.contact_phone or "010-0000-0000"
        client.contact_email = client.contact_email or "owner@example.com"
    filing = (
        await db.execute(
            select(MonthlyFiling).where(MonthlyFiling.period == "2026-04")
        )
    ).scalars().first()
    return client, filing


@pytest.mark.asyncio
async def test_invite_body_carries_permanent_portal_link(
    monkeypatch, http: AsyncClient
):
    """초대 발송 — SMS·이메일 본문에 상설 링크가 실리고, 그 링크가 실제로 열린다."""
    from app.db import SessionLocal
    from app.services import invite as invite_mod
    from app.services.portal import get_or_issue_portal_token

    capture = _CaptureChannel()
    monkeypatch.setattr(invite_mod, "get_sms_channel", lambda: capture)
    monkeypatch.setattr(invite_mod, "get_email_channel", lambda: capture)

    async with SessionLocal() as db:
        client, filing = await _client_and_filing(db, with_contact=True)
        await invite_mod.send_invite_to_client(db, filing, client, "테스트세무회계")
        token = (await get_or_issue_portal_token(db, client)).token
        await db.commit()

    assert len(capture.sent) == 2, "SMS와 이메일 두 경로 모두 발송돼야 한다"
    bodies = capture.bodies()
    assert f"/r/{token}" in bodies, "본문에 상설 링크가 없다"
    assert all(item["url"] and token in item["url"] for item in capture.sent)

    # 발송된 링크가 실제로 해석되는지 — 죽은 링크를 보내면 안 된다.
    resolved = await http.get(f"/api/v1/public/r/{token}")
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["accepting"] is True


@pytest.mark.asyncio
async def test_invite_link_is_identical_across_two_sends(monkeypatch, http: AsyncClient):
    """두 번 보내도 같은 링크여야 사장님이 저장해 둔 링크가 계속 쓰인다."""
    from app.db import SessionLocal
    from app.services import invite as invite_mod

    capture = _CaptureChannel()
    monkeypatch.setattr(invite_mod, "get_sms_channel", lambda: capture)
    monkeypatch.setattr(invite_mod, "get_email_channel", lambda: capture)

    async with SessionLocal() as db:
        client, filing = await _client_and_filing(db, with_contact=True)
        await invite_mod.send_invite_to_client(db, filing, client, "테스트세무회계")
        await invite_mod.send_invite_to_client(db, filing, client, "테스트세무회계")
        await db.commit()

    urls = {item["url"] for item in capture.sent}
    assert len(urls) == 1, f"발송마다 링크가 달라졌다: {urls}"


@pytest.mark.asyncio
async def test_confirmation_body_carries_permanent_portal_link(
    monkeypatch, http: AsyncClient
):
    """확인요청 발송도 같은 상설 링크를 쓴다."""
    from app.db import SessionLocal
    from app.models import CollectionSession, PayrollEntry
    from app.services import confirmation as confirmation_mod
    from app.services.portal import get_or_issue_portal_token

    capture = _CaptureChannel()
    monkeypatch.setattr(confirmation_mod, "get_sms_channel", lambda: capture)
    monkeypatch.setattr(confirmation_mod, "get_email_channel", lambda: capture)

    async with SessionLocal() as db:
        client, filing = await _client_and_filing(db, with_contact=True)
        session = (
            await db.execute(
                select(CollectionSession).where(
                    CollectionSession.monthly_filing_id == filing.id,
                    CollectionSession.client_id == client.id,
                )
            )
        ).scalars().first()
        entries = (
            await db.execute(
                select(PayrollEntry).where(
                    PayrollEntry.monthly_filing_id == filing.id,
                    PayrollEntry.client_id == client.id,
                )
            )
        ).scalars().all()

        sent, channel, error = await confirmation_mod.send_confirmation(
            db,
            session=session,
            client=client,
            filing=filing,
            entries=list(entries),
            office_name="테스트세무회계",
            channel="sms",
        )
        token = (await get_or_issue_portal_token(db, client)).token
        await db.commit()

    assert sent, f"확인요청 발송 실패: {channel} / {error}"
    assert f"/r/{token}" in capture.bodies()
