"""카카오 알림톡 발송.

Phase 1에서는 ``stub`` 드라이버만 동작합니다. 실제 발송은 발송대행사(알리고/NHN Toast)
계약 + 템플릿 등록 이후에 ``aligo`` / ``nhn_toast`` 드라이버를 채워 넣습니다.
"""

from __future__ import annotations

import logging
from uuid import uuid4

import httpx

from app.channels.base import MessageChannel, MessageRecipient, SendResult
from app.config import get_settings

logger = logging.getLogger(__name__)


class StubAlimtalkChannel(MessageChannel):
    name = "alimtalk_stub"

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(
        self,
        recipient: MessageRecipient,
        *,
        body: str,
        template_code: str | None = None,
        url: str | None = None,
    ) -> SendResult:
        msg_id = uuid4().hex
        self.sent.append(
            {
                "id": msg_id,
                "to_name": recipient.name,
                "phone": recipient.phone,
                "template_code": template_code,
                "body": body,
                "url": url,
            }
        )
        logger.info("[alimtalk-stub] → %s | %s | %s", recipient.name, recipient.phone, body[:60])
        return SendResult(channel=self.name, accepted=True, provider_msg_id=msg_id)


class AligoAlimtalkChannel(MessageChannel):
    """알리고 알림톡 발송 (실 발송용 — 계정/템플릿 등록 후 활성화)."""

    name = "alimtalk_aligo"

    def __init__(self) -> None:
        s = get_settings()
        self.api_key = s.aligo_api_key
        self.user_id = s.aligo_user_id
        self.sender_key = s.aligo_sender_key

    async def send(
        self,
        recipient: MessageRecipient,
        *,
        body: str,
        template_code: str | None = None,
        url: str | None = None,
    ) -> SendResult:
        if not (self.api_key and self.user_id and self.sender_key and template_code):
            return SendResult(
                channel=self.name,
                accepted=False,
                provider_msg_id=None,
                error="ALIGO 자격증명/템플릿코드 누락",
            )
        if not recipient.phone:
            return SendResult(
                channel=self.name, accepted=False, provider_msg_id=None, error="phone 필수"
            )

        async with httpx.AsyncClient(timeout=10.0) as cli:
            resp = await cli.post(
                "https://kakaoapi.aligo.in/akv10/alimtalk/send/",
                data={
                    "apikey": self.api_key,
                    "userid": self.user_id,
                    "senderkey": self.sender_key,
                    "tpl_code": template_code,
                    "sender": "",
                    "receiver_1": recipient.phone,
                    "recvname_1": recipient.name,
                    "subject_1": "원천세 자료 요청",
                    "message_1": body,
                },
            )
        ok = resp.status_code == 200 and (resp.json().get("code") in (0, "0"))
        return SendResult(
            channel=self.name,
            accepted=ok,
            provider_msg_id=str(resp.json().get("info", {}).get("msg_id", "")) or None,
            error=None if ok else resp.text[:200],
        )


class NhnCloudAlimtalkChannel(MessageChannel):
    """NHN Cloud Notification — 카카오 알림톡.

    문서: https://docs.nhncloud.com/ko/Notification/KakaoTalk%20Bizmessage/ko/api-guide/
    엔드포인트: ``https://api-alimtalk.cloud.toast.com/alimtalk/v2.3/appkeys/{appKey}/messages``
    """

    name = "alimtalk_nhn_cloud"

    def __init__(self) -> None:
        s = get_settings()
        self.app_key = s.nhn_cloud_app_key
        self.secret_key = s.nhn_cloud_secret_key
        self.sender_key = s.nhn_cloud_sender_key

    async def send(
        self,
        recipient: MessageRecipient,
        *,
        body: str,
        template_code: str | None = None,
        url: str | None = None,
    ) -> SendResult:
        if not (self.app_key and self.secret_key and self.sender_key and template_code):
            return SendResult(
                channel=self.name,
                accepted=False,
                provider_msg_id=None,
                error="NHN Cloud 자격증명/템플릿코드 누락",
            )
        if not recipient.phone:
            return SendResult(
                channel=self.name, accepted=False, provider_msg_id=None, error="phone 필수"
            )

        endpoint = (
            f"https://api-alimtalk.cloud.toast.com/alimtalk/v2.3/appkeys/{self.app_key}/messages"
        )
        payload = {
            "senderKey": self.sender_key,
            "templateCode": template_code,
            "recipientList": [
                {
                    "recipientNo": recipient.phone.replace("-", ""),
                    "content": body,
                    "recipientGroupingKey": recipient.name,
                }
            ],
        }
        async with httpx.AsyncClient(timeout=10.0) as cli:
            resp = await cli.post(
                endpoint,
                headers={"X-Secret-Key": self.secret_key, "Content-Type": "application/json"},
                json=payload,
            )
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            data = {}
        ok = resp.status_code == 200 and bool(data.get("header", {}).get("isSuccessful"))
        msg_id = None
        if ok:
            msgs = data.get("message", {}).get("data", {}).get("sendResults", [])
            if msgs:
                msg_id = str(msgs[0].get("messageId") or "")
        return SendResult(
            channel=self.name,
            accepted=ok,
            provider_msg_id=msg_id,
            error=None if ok else (data.get("header", {}).get("resultMessage") or resp.text[:200]),
        )


def get_alimtalk_channel() -> MessageChannel:
    s = get_settings()
    if s.kakao_alimtalk_provider == "nhn_cloud":
        return NhnCloudAlimtalkChannel()
    if s.kakao_alimtalk_provider == "aligo":
        return AligoAlimtalkChannel()
    return StubAlimtalkChannel()
