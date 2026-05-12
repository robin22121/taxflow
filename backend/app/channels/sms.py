"""SMS 발송 채널.

알림톡이 거부된 경우(미수신 거래처·템플릿 미일치) fallback 으로 사용.
Phase 1에서는 Aligo + Stub 두 드라이버를 지원합니다.
NHN Cloud SMS 등 추가 드라이버는 동일 인터페이스로 확장하세요.
"""

from __future__ import annotations

import logging
from uuid import uuid4

import httpx

from app.channels.base import MessageChannel, MessageRecipient, SendResult
from app.config import get_settings

logger = logging.getLogger(__name__)


def _strip_phone(phone: str) -> str:
    return phone.replace("-", "").replace(" ", "")


class StubSmsChannel(MessageChannel):
    name = "sms_stub"

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
            {"id": msg_id, "phone": recipient.phone, "body": body, "url": url}
        )
        logger.info("[sms-stub] → %s | %s", recipient.phone, body[:60])
        return SendResult(channel=self.name, accepted=True, provider_msg_id=msg_id)


class AligoSmsChannel(MessageChannel):
    """Aligo SMS — 알림톡과 동일 계정으로 사용 가능.

    엔드포인트: https://apis.aligo.in/send/
    msg_type 자동 분기: 90바이트 이하 SMS, 초과 시 LMS.
    """

    name = "sms_aligo"

    def __init__(self) -> None:
        s = get_settings()
        self.api_key = s.aligo_api_key
        self.user_id = s.aligo_user_id
        self.sender = s.aligo_sms_sender

    async def send(
        self,
        recipient: MessageRecipient,
        *,
        body: str,
        template_code: str | None = None,
        url: str | None = None,
    ) -> SendResult:
        if not (self.api_key and self.user_id and self.sender):
            missing = [
                k for k, v in {
                    "ALIGO_API_KEY": self.api_key,
                    "ALIGO_USER_ID": self.user_id,
                    "ALIGO_SMS_SENDER": self.sender,
                }.items() if not v
            ]
            logger.warning("[sms-aligo] config missing: %s", missing)
            return SendResult(
                channel=self.name,
                accepted=False,
                provider_msg_id=None,
                error=f"ALIGO 자격증명/발신번호 누락: {', '.join(missing)}",
            )
        if not recipient.phone:
            return SendResult(
                channel=self.name, accepted=False, provider_msg_id=None, error="phone 필수"
            )

        # 본문 길이 기반 자동 분기 (utf-8 바이트 길이 기준 — 한글 ~3byte/자)
        msg_type = "SMS" if len(body.encode("utf-8")) <= 90 else "LMS"
        sender_clean = _strip_phone(self.sender)
        receiver_clean = _strip_phone(recipient.phone)
        logger.info(
            "[sms-aligo] sending %s → sender=%s receiver=%s len=%dB",
            msg_type, sender_clean, receiver_clean, len(body.encode("utf-8")),
        )
        async with httpx.AsyncClient(timeout=10.0) as cli:
            resp = await cli.post(
                "https://apis.aligo.in/send/",
                data={
                    "key": self.api_key,
                    "user_id": self.user_id,
                    "sender": sender_clean,
                    "receiver": receiver_clean,
                    "msg": body,
                    "msg_type": msg_type,
                    "title": "원천세 자료 요청" if msg_type != "SMS" else "",
                    "testmode_yn": "N",
                },
            )
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            data = {}
        # Aligo: result_code=1 이면 성공, 그 외 실패
        result_code = str(data.get("result_code", ""))
        ok = resp.status_code == 200 and result_code == "1"
        if ok:
            logger.info(
                "[sms-aligo] accepted msg_id=%s", data.get("msg_id"),
            )
        else:
            logger.warning(
                "[sms-aligo] rejected status=%s result_code=%s message=%s",
                resp.status_code, result_code, data.get("message") or resp.text[:200],
            )
        return SendResult(
            channel=self.name,
            accepted=ok,
            provider_msg_id=str(data.get("msg_id", "")) or None,
            error=None if ok else (data.get("message") or resp.text[:200]),
        )


def get_sms_channel() -> MessageChannel:
    s = get_settings()
    if s.sms_provider == "aligo":
        return AligoSmsChannel()
    return StubSmsChannel()
