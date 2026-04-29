"""Email channel.

우선순위 (``EMAIL_PROVIDER=auto`` 기본):
1. NCP Cloud Outbound Mailer — NCP 자격증명이 채워져 있으면 사용
2. SendGrid — SENDGRID_API_KEY 가 있으면 사용
3. Stub — 위 둘 다 없으면 dev용 stub
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
from uuid import uuid4

import httpx

from app.channels.base import MessageChannel, MessageRecipient, SendResult
from app.config import get_settings

logger = logging.getLogger(__name__)


class StubEmailChannel(MessageChannel):
    name = "email_stub"

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, recipient, *, body, template_code=None, url=None) -> SendResult:
        msg_id = uuid4().hex
        self.sent.append(
            {"id": msg_id, "email": recipient.email, "body": body, "url": url}
        )
        logger.info("[email-stub] → %s | %s", recipient.email, body[:60])
        return SendResult(channel=self.name, accepted=True, provider_msg_id=msg_id)


class SendGridEmailChannel(MessageChannel):
    name = "email_sendgrid"

    def __init__(self) -> None:
        s = get_settings()
        self.api_key = s.sendgrid_api_key
        self.from_email = s.sendgrid_from_email

    async def send(
        self, recipient: MessageRecipient, *, body, template_code=None, url=None
    ) -> SendResult:
        if not (self.api_key and self.from_email and recipient.email):
            return SendResult(
                channel=self.name,
                accepted=False,
                provider_msg_id=None,
                error="SendGrid config or recipient email missing",
            )
        async with httpx.AsyncClient(timeout=10.0) as cli:
            resp = await cli.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "personalizations": [{"to": [{"email": recipient.email}]}],
                    "from": {"email": self.from_email},
                    "subject": "원천세 자료 요청",
                    "content": [{"type": "text/plain", "value": body}],
                },
            )
        return SendResult(
            channel=self.name,
            accepted=resp.status_code in (200, 202),
            provider_msg_id=resp.headers.get("x-message-id"),
            error=None if resp.status_code in (200, 202) else resp.text[:200],
        )


class NcpOutboundMailerChannel(MessageChannel):
    """NCP Cloud Outbound Mailer.

    문서: https://api.ncloud-docs.com/docs/ai-application-service-cloudoutboundmailer-cloudoutboundmailer
    Auth: HMAC-SHA256 with access/secret keys.
    """

    name = "email_ncp_outbound"
    HOST = "https://mail.apigw.ntruss.com"
    PATH = "/api/v1/mails"

    def __init__(self) -> None:
        s = get_settings()
        self.access_key = s.ncp_outbound_access_key
        self.secret_key = s.ncp_outbound_secret_key
        self.sender_address = s.ncp_outbound_sender_address
        self.sender_name = s.ncp_outbound_sender_name

    def _sign(self, method: str, path: str, ts: str) -> str:
        msg = f"{method} {path}\n{ts}\n{self.access_key}".encode("utf-8")
        sig = hmac.new(self.secret_key.encode("utf-8"), msg, hashlib.sha256).digest()
        return base64.b64encode(sig).decode("utf-8")

    async def send(
        self, recipient: MessageRecipient, *, body, template_code=None, url=None
    ) -> SendResult:
        if not (self.access_key and self.secret_key and self.sender_address and recipient.email):
            return SendResult(
                channel=self.name,
                accepted=False,
                provider_msg_id=None,
                error="NCP Outbound Mailer config or recipient email missing",
            )
        ts = str(int(time.time() * 1000))
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "x-ncp-apigw-timestamp": ts,
            "x-ncp-iam-access-key": self.access_key,
            "x-ncp-apigw-signature-v2": self._sign("POST", self.PATH, ts),
        }
        payload = {
            "senderAddress": self.sender_address,
            "senderName": self.sender_name,
            "title": "원천세 자료 요청",
            "body": body,
            "recipients": [
                {
                    "address": recipient.email,
                    "name": recipient.name or recipient.email,
                    "type": "R",
                }
            ],
            "individual": True,
            "advertising": False,
        }
        async with httpx.AsyncClient(timeout=10.0) as cli:
            resp = await cli.post(self.HOST + self.PATH, headers=headers, json=payload)
        ok = resp.status_code in (200, 201)
        request_id = None
        if ok:
            try:
                request_id = str(resp.json().get("requestId", ""))
            except Exception:  # noqa: BLE001
                pass
        return SendResult(
            channel=self.name,
            accepted=ok,
            provider_msg_id=request_id,
            error=None if ok else resp.text[:200],
        )


def get_email_channel() -> MessageChannel:
    s = get_settings()
    p = s.email_provider
    if p == "ncp_outbound":
        return NcpOutboundMailerChannel()
    if p == "sendgrid":
        return SendGridEmailChannel()
    if p == "stub":
        return StubEmailChannel()
    # auto
    if s.ncp_outbound_access_key and s.ncp_outbound_secret_key and s.ncp_outbound_sender_address:
        return NcpOutboundMailerChannel()
    if s.sendgrid_api_key:
        return SendGridEmailChannel()
    return StubEmailChannel()
