"""AI 도우미 — 자유 질의응답, multi-provider (Gemini / Claude).

`frontend/.../filings/[id]/page.tsx` 의 `QAAssistantDialog` 팝업(사용법/법령/고객응대 3탭)이
호출하는 백엔드. `ai_parser.py` 와 달리 구조화 출력이 아니라 자유 텍스트 답변을 반환한다.

법령(law) 탭은 국가법령정보 공동활용(law.go.kr) API로 관련 조문을 찾아 grounding 자료로
LLM에 넣는다(`law_search.build_law_context`). OC(`settings.lawgokr_oc`)가 비어 있거나 조문을
못 찾으면 학습된 지식만으로 답하고 원문 확인을 권고하는 문구를 덧붙인다.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

import httpx

from app.config import get_settings
from app.services import law_search

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
        "[제1원칙] 답변은 반드시 법령·예규·판례·해석 등 근거에 기반해서 답하고, 확실하지 않은 "
        "내용을 추측해서 답하지 마세요. 이번 질문에는 관련 조문을 찾지 못해 근거 자료 없이 "
        "답해야 하는 상황입니다 — 자신 없는 내용은 '확인 필요'라고 밝히고, 그래도 답하는 부분은 "
        "전부 '(이것은 AI의 판단이며 틀릴 수 있습니다)'를 붙이세요. 국세법령정보시스템 등 원문으로 "
        "반드시 재확인하라는 안내를 답변 끝에 덧붙이세요.\n"
        "[제2원칙] 질문과 직접 관련된 내용만 다루고, 관련 없는 법령·논점을 끌어오지 마세요."
    ),
    "customer": (
        "당신은 세무사사무소 담당자가 수임업체(고객사) 카카오톡 문의에 답할 때 쓸 답변 초안을 "
        "작성하는 도우미입니다.\n"
        "친절하고 이해하기 쉬운 문장으로, 고객에게 그대로 복사해 붙여넣을 수 있는 완성도로 작성하세요.\n"
        "전문 용어는 풀어서 설명하고, 확정적이지 않은 세액·기한은 단정하지 말고 "
        "'확인 후 다시 안내드리겠다' 식으로 여지를 두세요."
    ),
}

_LAW_GROUNDED_SYSTEM_PROMPT = (
    "당신은 한국 세무사사무소 담당자를 돕는 세법 Q&A 도우미입니다.\n"
    "질문과 함께 국가법령정보 공동활용 API에서 가져온 관련 조문 원문이 주어집니다.\n"
    "[제1원칙] 답변은 반드시 아래 제공된 조문(향후 예규·판례·해석도 포함될 수 있음)에 근거해서 "
    "답하고, 확실하지 않은 내용을 추측해서 답하지 마세요. 질문에 대해 현행 법상 어떻게 규정되어 "
    "있는지 먼저 조문을 인용해 설명하세요. 조문 해석·적용에 당신의 판단이나 의견이 들어가는 "
    "경우, 그 구절에는 반드시 '(이것은 AI의 판단이며 틀릴 수 있습니다)'라고 명시하세요. 제공된 "
    "조문만으로 답하기 부족하면 억지로 답하지 말고 그 사실을 분명히 밝히세요. 조문에 없는 "
    "세율·금액·기한을 단정하지 마세요.\n"
    "[제2원칙] 질문과 직접 관련된 조문만 근거로 쓰고, 관련 없는 조문을 끌어와 답을 늘리지 마세요."
)

_SEARCH_TERM_PROMPT = (
    "다음 질문에서 한국 법령 조문을 검색할 핵심 키워드를 2~6개, 쉼표로만 구분해 출력하세요.\n"
    "질문의 구어체 표현은 법령 원문에서 실제로 쓰는 용어로 바꿔 제시하세요 "
    "(예: '상실기한' → 상실 신고, 취득 신고 / '퇴사' → 퇴직, 상실 / '4대보험' → 국민연금, "
    "건강보험, 고용보험, 산재보험).\n"
    "키워드 목록 외에는 아무것도 출력하지 마세요."
)


async def _extract_search_terms(question: str, provider: str, settings: Any) -> list[str]:
    """질문을 법령 원문에 가까운 검색어로 바꾼다 (law_search 의 단순 토큰 매칭 보강).

    담당자 질문은 구어체("상실기한")인데 법령 원문은 다른 표현("상실 신고")을 써서
    토큰 그대로는 못 찾는 경우가 많다 — LLM 한 번 더 호출해 법률 용어로 바꿔준다.
    실패해도 기존 토큰 매칭으로 자연히 폴백되므로 조용히 빈 리스트를 반환한다.
    """
    try:
        if provider == "gemini":
            text = await _answer_with_gemini(_SEARCH_TERM_PROMPT, question, [], settings)
        elif provider == "anthropic":
            text = await _answer_with_anthropic(_SEARCH_TERM_PROMPT, question, [], settings)
        else:
            return []
    except (RuntimeError, httpx.HTTPError):
        logger.warning("law search term extraction failed", exc_info=True)
        return []
    return [w.strip() for w in re.split(r"[,\n、，]+", text) if w.strip()]


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
    question_for_llm = question

    if intent == "law" and settings.lawgokr_oc:
        search_terms = await _extract_search_terms(question, provider, settings)
        try:
            law_context = await law_search.build_law_context(
                question, settings.lawgokr_oc, extra_keywords=search_terms
            )
        except httpx.HTTPError:
            logger.warning("law.go.kr lookup failed, falling back to ungrounded answer", exc_info=True)
            law_context = ""
        if law_context:
            system_prompt = _LAW_GROUNDED_SYSTEM_PROMPT
            question_for_llm = f"[관련 조문]\n{law_context}\n\n[질문]\n{question}"

    trimmed_history = (history or [])[-_MAX_HISTORY:]

    if provider == "gemini":
        return await _answer_with_gemini(system_prompt, question_for_llm, trimmed_history, settings)
    elif provider == "anthropic":
        return await _answer_with_anthropic(system_prompt, question_for_llm, trimmed_history, settings)
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
