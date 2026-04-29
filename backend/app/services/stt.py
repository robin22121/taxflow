"""Speech-to-Text — 1순위 NCP CLOVA Speech, fallback Whisper Large-v3.

CLOVA Speech "외부 호출" 모드를 사용합니다. 통화 녹음 파일을 NCP Object Storage에 올린 뒤
객체 URL을 invoke API에 전달하면 결과 텍스트가 반환됩니다.

문서: https://api.ncloud-docs.com/docs/ai-application-service-clovaspeech
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class STTResult:
    text: str
    provider: str
    confidence: float | None = None
    raw: dict[str, Any] | None = None


class STTProvider(ABC):
    name: str

    @abstractmethod
    async def transcribe(
        self, *, audio_url: str | None = None, audio_bytes: bytes | None = None
    ) -> STTResult: ...


class StubSTT(STTProvider):
    name = "stub"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        # Tests can pre-load a canned response.
        self.canned: str = "(stub STT result — set StubSTT.canned in tests)"

    async def transcribe(
        self, *, audio_url: str | None = None, audio_bytes: bytes | None = None
    ) -> STTResult:
        self.calls.append({"url": audio_url, "bytes_len": len(audio_bytes or b"")})
        return STTResult(text=self.canned, provider=self.name)


class ClovaSpeechSTT(STTProvider):
    """CLOVA Speech 외부 호출.

    - ``audio_url``로 호출하면 ``url`` 모드로 전송 (NCP Object Storage 객체 URL).
    - ``audio_bytes``는 임시 업로드 후 호출하는 보다 복잡한 흐름이므로 별도 헬퍼에서 처리.
    """

    name = "clova"

    def __init__(self) -> None:
        s = get_settings()
        self.invoke_url = s.clova_invoke_url
        self.secret_key = s.clova_secret_key

    async def transcribe(
        self, *, audio_url: str | None = None, audio_bytes: bytes | None = None
    ) -> STTResult:
        if not (self.invoke_url and self.secret_key):
            raise RuntimeError("CLOVA_INVOKE_URL / CLOVA_SECRET_KEY 가 설정되지 않았습니다")
        if not audio_url:
            raise ValueError(
                "ClovaSpeechSTT: audio_url 필수 (bytes 입력은 별도 업로드 헬퍼 사용)"
            )

        params = {
            "language": "ko-KR",
            "completion": "sync",
            "url": audio_url,
            "wordAlignment": False,
            "fullText": True,
        }
        async with httpx.AsyncClient(timeout=120.0) as cli:
            resp = await cli.post(
                self.invoke_url + "/recognizer/url",
                headers={"X-CLOVASPEECH-API-KEY": self.secret_key},
                json=params,
            )
        if resp.status_code != 200:
            raise RuntimeError(f"CLOVA Speech 실패: {resp.status_code} {resp.text[:200]}")
        data = resp.json()
        text = data.get("text") or "".join(s.get("text", "") for s in data.get("segments", []))
        return STTResult(text=text, provider=self.name, raw=data)


def get_stt_provider() -> STTProvider:
    s = get_settings()
    if s.stt_provider == "clova":
        return ClovaSpeechSTT()
    if s.stt_provider == "whisper":
        # Whisper Large-v3 self-hosted or via OpenAI — Phase 2.
        # 현재는 stub으로 떨어짐. (구현 시 WhisperSTT 클래스 추가)
        logger.warning("STT_PROVIDER=whisper but Whisper driver not yet implemented; using stub")
    return StubSTT()


__all__ = ["ClovaSpeechSTT", "STTProvider", "STTResult", "StubSTT", "get_stt_provider"]
