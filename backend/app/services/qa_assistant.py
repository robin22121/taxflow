"""AI 도우미 — 자유 질의응답, multi-provider (Gemini / Claude).

`frontend/.../filings/[id]/page.tsx` 의 `QAAssistantDialog` 팝업(사용법/법령/고객응대 3탭)이
호출하는 백엔드. `ai_parser.py` 와 달리 구조화 출력이 아니라 자유 텍스트 답변을 반환한다.

법령(law) 탭은 아직 법령 MCP(국가법령정보센터 등)와 연결되어 있지 않다 — 학습된 지식 기반
답변이므로 시스템 프롬프트에서 원문 확인을 권고하도록 지시한다. MCP 연결은 후속 작업.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from app.config import get_settings

logger = logging.getLogger(__name__)

QaIntent = Literal["howto", "law", "customer"]

_MAX_HISTORY = 10

_SYSTEM_PROMPTS: dict[QaIntent, str] = {
    "howto": (
        "당신은 한국 세무사사무소 담당자를 돕는 '이지원천' 서비스 사용법 도우미입니다.\n"
        "이지원천(사장님 포털 포함), 위하고T, 홈택스, 4대보험 EDI, 각종 증명원 발급 등 "
        "본 서비스의 화면·기능·조작 절차를 정확하고 간결하게 설명하세요.\n"
        "확실하지 않은 화면 위치나 절차는 추측하지 말고, 담당자에게 직접 확인이 필요하다고 안내하세요."
    ),
    "law": (
        "당신은 한국 세무사사무소 담당자를 돕는 세법 Q&A 도우미입니다.\n"
        "소득세·부가가치세·원천세·상속세·4대보험 등과 관련된 조문·시행령·시행규칙·예규·판례·서식을 "
        "근거로 정확하게 답변하세요.\n"
        "주의: 실시간 법령 검색(MCP)이 아직 연결되어 있지 않아 학습된 지식에 기반한 답변입니다. "
        "최신 개정 여부·세부 기한·세율은 국세법령정보시스템 등 원문으로 반드시 재확인하라는 안내를 "
        "답변 끝에 짧게 덧붙이세요."
    ),
    "customer": (
        "당신은 세무사사무소 담당자가 수임업체(고객사) 카카오톡 문의에 답할 때 쓸 답변 초안을 "
        "작성하는 도우미입니다.\n"
        "친절하고 이해하기 쉬운 문장으로, 고객에게 그대로 복사해 붙여넣을 수 있는 완성도로 작성하세요.\n"
        "전문 용어는 풀어서 설명하고, 확정적이지 않은 세액·기한은 단정하지 말고 "
        "'확인 후 다시 안내드리겠다' 식으로 여지를 두세요."
    ),
}


async def answer_question(
    question: str,
    *,
    intent: QaIntent,
    history: list[dict[str, str]] | None = None,
    provider: str | None = None,
) -> str:
    """자유 질문에 답한다.

    Args:
        question: 담당자가 입력한 질문.
        intent: "howto" | "law" | "customer" — 답변 관점.
        history: 이전 대화 ``[{"role": "user"|"assistant", "content": ...}, ...]``.
        provider: "gemini" | "anthropic" (기본: config의 ai_provider)
    """
    settings = get_settings()
    provider = provider or settings.ai_provider
    system_prompt = _SYSTEM_PROMPTS[intent]
    trimmed_history = (history or [])[-_MAX_HISTORY:]

    if provider == "gemini":
        return await _answer_with_gemini(system_prompt, question, trimmed_history, settings)
    elif provider == "anthropic":
        return await _answer_with_anthropic(system_prompt, question, trimmed_history, settings)
    else:
        raise ValueError(f"Unknown AI provider: {provider}")


async def _answer_with_gemini(
    system_prompt: str,
    question: str,
    history: list[dict[str, str]],
    settings: Any,
) -> str:
    from google import genai

    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")

    client = genai.Client(api_key=settings.gemini_api_key)

    contents = [
        {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
        for m in history
    ]
    contents.append({"role": "user", "parts": [{"text": question}]})

    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=contents,
        config=genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.3,
        ),
    )
    return response.text or ""


async def _answer_with_anthropic(
    system_prompt: str,
    question: str,
    history: list[dict[str, str]],
    settings: Any,
) -> str:
    from anthropic import AsyncAnthropic

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": question})

    response = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2048,
        system=system_prompt,
        messages=messages,
    )
    return "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )


__all__ = ["QaIntent", "answer_question"]
