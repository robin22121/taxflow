"""Abstract messaging channel interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(slots=True)
class MessageRecipient:
    name: str
    phone: str | None = None
    email: str | None = None
    kakao_channel_id: str | None = None


@dataclass(slots=True)
class SendResult:
    channel: str
    accepted: bool
    provider_msg_id: str | None
    error: str | None = None


class MessageChannel(ABC):
    name: str

    @abstractmethod
    async def send(
        self,
        recipient: MessageRecipient,
        *,
        body: str,
        template_code: str | None = None,
        url: str | None = None,
    ) -> SendResult: ...
