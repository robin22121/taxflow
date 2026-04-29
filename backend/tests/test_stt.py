"""STT provider tests — only the stub is exercised; CLOVA requires live creds."""

import os

import pytest

from app.services.stt import ClovaSpeechSTT, StubSTT, get_stt_provider


@pytest.mark.asyncio
async def test_stub_returns_canned():
    s = StubSTT()
    s.canned = "안녕하세요 김연호 100 만원 입니다"
    res = await s.transcribe(audio_url="https://example.com/x.wav")
    assert res.text == "안녕하세요 김연호 100 만원 입니다"
    assert res.provider == "stub"
    assert s.calls[0]["url"] == "https://example.com/x.wav"


def test_get_stt_provider_default_stub():
    os.environ["STT_PROVIDER"] = "stub"
    from app.config import get_settings

    get_settings.cache_clear()
    p = get_stt_provider()
    assert isinstance(p, StubSTT)


@pytest.mark.asyncio
async def test_clova_requires_credentials():
    os.environ["STT_PROVIDER"] = "clova"
    os.environ["CLOVA_INVOKE_URL"] = ""
    os.environ["CLOVA_SECRET_KEY"] = ""
    from app.config import get_settings

    get_settings.cache_clear()
    p = ClovaSpeechSTT()
    with pytest.raises(RuntimeError):
        await p.transcribe(audio_url="https://example.com/x.wav")

    # restore
    os.environ["STT_PROVIDER"] = "stub"
    get_settings.cache_clear()
