"""AI payroll parser — multi-provider (Gemini / Claude).

Takes raw text from a client (카톡 답장, 이메일 본문, 통화 STT 출력) plus the client's
employee master + previous month payroll, and returns a structured payroll snapshot
with matching/anomaly classifications.

Provider selection:
- ``AI_PROVIDER=gemini`` (default): Google Gemini Flash — fast, cheap, excellent Korean
- ``AI_PROVIDER=anthropic``: Claude Sonnet — fallback, proven structured output

The AI does NOT do final tax calc — that's deterministic in ``tax_calc.py`` post-parse.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.config import get_settings
from app.services.pii import redact_payload, redact_pii

logger = logging.getLogger(__name__)


# --- Public schema ---------------------------------------------------------


@dataclass(slots=True)
class MatchedEmployee:
    name: str
    employee_id: str
    amount: int
    non_taxable: int = 0
    meal_amount: int = 0
    car_amount: int = 0
    childcare_amount: int = 0
    income_type: str = "WAGE"
    change_from_prev: int | None = None
    change_reason: str | None = None


@dataclass(slots=True)
class NewHireSuspected:
    name: str
    amount: int
    non_taxable: int = 0
    meal_amount: int = 0
    car_amount: int = 0
    childcare_amount: int = 0
    income_type: str = "WAGE"
    needs_confirmation: bool = True


@dataclass(slots=True)
class ResignationSuspected:
    employee_id: str
    name: str
    reason: str  # "이번달 누락" / "회사가 직접 언급"


@dataclass(slots=True)
class AmbiguousItem:
    raw_text: str
    issue: str


@dataclass(slots=True)
class RelativeReference:
    text: str
    applied: bool
    note: str | None = None


@dataclass(slots=True)
class PayrollParsingResult:
    matched_employees: list[MatchedEmployee] = field(default_factory=list)
    new_hire_suspected: list[NewHireSuspected] = field(default_factory=list)
    resignation_suspected: list[ResignationSuspected] = field(default_factory=list)
    ambiguous_items: list[AmbiguousItem] = field(default_factory=list)
    relative_references: list[RelativeReference] = field(default_factory=list)
    raw_response: dict[str, Any] | None = None


# --- Shared prompt ---------------------------------------------------------

_SYSTEM_PROMPT = """당신은 한국 세무사사무소의 원천세 자료 정형화 어시스턴트입니다.

[입력]
- 거래처(고객사)가 비정형 텍스트로 보낸 이번 달 인건비/지급액 자료
- 거래처의 직원 마스터(이름·식별자) 와 이전 달 지급액

[당신의 역할]
1. 본문에서 인명·금액·소득구분을 추출합니다.
2. 직원 마스터와 매칭합니다 (정확/유사/누락).
3. "저번 달이랑 똑같아요" 같은 상대 표현은 이전 달 데이터를 그대로 적용한 것으로 표시합니다.
4. 신규/퇴사 가능성을 분류합니다 — 결정은 사람에게 맡기고 당신은 의심자만 표시합니다.

[규칙]
- 금액은 만원 단위 표기("100", "1.2백만") 도 정수 원 단위로 환산합니다 (100만원 → 1000000).
- 비과세소득이 명시되지 않으면 0.
- 비과세 항목이 구체적으로 명시되면 분리해서 채웁니다:
  * "식대 20만원" → meal_amount: 200000 (한도 200000)
  * "자가운전보조금 20만원" / "차량유지비" → car_amount: 200000 (한도 200000)
  * "육아수당" / "보육수당" → childcare_amount (한도 200000, 6세 이하 자녀)
  * non_taxable 은 위 셋의 합과 일치시키거나, 분류 불가능한 비과세까지 포함한 총액.
- 소득구분이 명확하지 않으면 ``WAGE`` 로 둡니다.
- 추측한 부분은 ``ambiguous_items`` 에 함께 표시합니다.
- 직원 마스터에 없는 이름이 나오면 ``new_hire_suspected``.
- 마스터에는 있는데 이번 달 입력에서 빠진 직원은 ``resignation_suspected``.
- 동명이인이면 ``ambiguous_items`` 로.
"""

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "matched_employees": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "employee_id": {"type": "string"},
                    "amount": {"type": "integer"},
                    "non_taxable": {"type": "integer"},
                    "meal_amount": {"type": "integer", "description": "식대 (한도 20만)"},
                    "car_amount": {"type": "integer", "description": "자가운전보조금 (한도 20만)"},
                    "childcare_amount": {"type": "integer", "description": "육아수당 (한도 20만)"},
                    "income_type": {
                        "type": "string",
                        "enum": ["WAGE", "BUSINESS", "OTHER", "DAILY", "RETIREMENT"],
                    },
                    "change_from_prev": {"type": "integer"},
                    "change_reason": {"type": "string"},
                },
                "required": ["name", "employee_id", "amount"],
            },
        },
        "new_hire_suspected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "amount": {"type": "integer"},
                    "non_taxable": {"type": "integer"},
                    "meal_amount": {"type": "integer"},
                    "car_amount": {"type": "integer"},
                    "childcare_amount": {"type": "integer"},
                    "income_type": {
                        "type": "string",
                        "enum": ["WAGE", "BUSINESS", "OTHER", "DAILY", "RETIREMENT"],
                    },
                    "needs_confirmation": {"type": "boolean"},
                },
                "required": ["name", "amount"],
            },
        },
        "resignation_suspected": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "employee_id": {"type": "string"},
                    "name": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["employee_id", "name", "reason"],
            },
        },
        "ambiguous_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "raw_text": {"type": "string"},
                    "issue": {"type": "string"},
                },
                "required": ["raw_text", "issue"],
            },
        },
        "relative_references": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "applied": {"type": "boolean"},
                    "note": {"type": "string"},
                },
                "required": ["text", "applied"],
            },
        },
    },
    "required": [
        "matched_employees",
        "new_hire_suspected",
        "resignation_suspected",
        "ambiguous_items",
        "relative_references",
    ],
}


# --- Main entry point (provider-agnostic) -----------------------------------


async def parse_payroll_message(
    raw_text: str,
    *,
    client_name: str,
    employee_master: list[dict[str, Any]],
    previous_month_data: list[dict[str, Any]],
    period: str,
    provider: str | None = None,
    **kwargs: Any,
) -> PayrollParsingResult:
    """Parse a raw client message into structured payroll data.

    Args:
        raw_text: 카톡/이메일/통화-STT 결과 등 비정형 텍스트.
        client_name: 거래처(사업자) 이름.
        employee_master: ``[{"id":..., "name":..., "last_amount":...}, ...]``
        previous_month_data: ``[{"name":..., "employee_id":..., "amount":...}, ...]``
        period: ``"YYYY-MM"``
        provider: "gemini" | "anthropic" (기본: config의 ai_provider)
    """
    settings = get_settings()
    provider = provider or settings.ai_provider

    # PII 가드
    safe_text = redact_pii(raw_text)
    safe_master = redact_payload(employee_master)
    safe_prev = redact_payload(previous_month_data)

    context = (
        f"[거래처] {client_name}\n"
        f"[직원 마스터]\n{json.dumps(safe_master, ensure_ascii=False, indent=2)}\n\n"
        f"[이전 달 데이터]\n{json.dumps(safe_prev, ensure_ascii=False, indent=2)}"
    )

    user_message = (
        f"[지급년월] {period}\n\n"
        f"[이번 달 메시지]\n{safe_text}\n\n"
        "위 메시지를 분석해 결과를 JSON으로 반환하세요."
    )

    if provider == "gemini":
        return await _parse_with_gemini(context, user_message, settings, **kwargs)
    elif provider == "anthropic":
        return await _parse_with_anthropic(context, user_message, settings, **kwargs)
    else:
        raise ValueError(f"Unknown AI provider: {provider}")


# --- Gemini backend ---------------------------------------------------------


async def _parse_with_gemini(
    context: str,
    user_message: str,
    settings: Any,
    **kwargs: Any,
) -> PayrollParsingResult:
    from google import genai

    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")

    client = genai.Client(api_key=settings.gemini_api_key)
    model = kwargs.get("model") or settings.gemini_model

    full_prompt = f"{context}\n\n{user_message}"

    response = await client.aio.models.generate_content(
        model=model,
        contents=full_prompt,
        config=genai.types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=_OUTPUT_SCHEMA,
            temperature=0.1,
        ),
    )

    return _parse_json_response(response.text)


# --- Anthropic backend ------------------------------------------------------


async def _parse_with_anthropic(
    context: str,
    user_message: str,
    settings: Any,
    **kwargs: Any,
) -> PayrollParsingResult:
    from anthropic import AsyncAnthropic

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    client = kwargs.get("client") or AsyncAnthropic(api_key=settings.anthropic_api_key)
    model = kwargs.get("model") or settings.anthropic_model

    tool_schema = {
        "name": "submit_payroll_parsing",
        "description": "이번 달 인건비 자료의 구조화 결과를 제출합니다.",
        "input_schema": _OUTPUT_SCHEMA,
    }

    response = await client.messages.create(
        model=model,
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[tool_schema],
        tool_choice={"type": "tool", "name": "submit_payroll_parsing"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": context,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {"type": "text", "text": user_message},
                ],
            }
        ],
    )

    # Extract tool_use block
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "tool_use":
            data = block.input or {}
            return _build_result(data)

    logger.warning("Anthropic: no tool_use block in response")
    return PayrollParsingResult()


# --- Response parsing -------------------------------------------------------


def _parse_json_response(text: str) -> PayrollParsingResult:
    """Parse JSON text response (from Gemini structured output)."""
    if not text:
        logger.warning("AI parser: empty response text")
        return PayrollParsingResult()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("AI parser: invalid JSON: %s", text[:500])
        return PayrollParsingResult()
    return _build_result(data)


def _safe_init(cls: type, data: dict[str, Any]) -> Any:
    """Construct a dataclass instance, ignoring unexpected keys from AI."""
    import dataclasses
    valid_fields = {f.name for f in dataclasses.fields(cls)}
    filtered = {k: v for k, v in data.items() if k in valid_fields}
    try:
        return cls(**filtered)
    except (TypeError, ValueError) as e:
        logger.warning("AI parser: failed to init %s with %s: %s", cls.__name__, filtered, e)
        return None


def _build_result(data: dict[str, Any]) -> PayrollParsingResult:
    """Build PayrollParsingResult from parsed dict."""
    def _parse_list(cls: type, items: list) -> list:
        return [obj for x in items if (obj := _safe_init(cls, x)) is not None]

    return PayrollParsingResult(
        matched_employees=_parse_list(MatchedEmployee, data.get("matched_employees", [])),
        new_hire_suspected=_parse_list(NewHireSuspected, data.get("new_hire_suspected", [])),
        resignation_suspected=_parse_list(ResignationSuspected, data.get("resignation_suspected", [])),
        ambiguous_items=_parse_list(AmbiguousItem, data.get("ambiguous_items", [])),
        relative_references=_parse_list(RelativeReference, data.get("relative_references", [])),
        raw_response=data,
    )


__all__ = [
    "AmbiguousItem",
    "MatchedEmployee",
    "NewHireSuspected",
    "PayrollParsingResult",
    "RelativeReference",
    "ResignationSuspected",
    "parse_payroll_message",
]
