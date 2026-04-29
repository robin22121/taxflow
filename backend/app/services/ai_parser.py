"""AI payroll parser using Claude.

Takes raw text from a client (카톡 답장, 이메일 본문, 통화 STT 출력) plus the client's
employee master + previous month payroll, and returns a structured payroll snapshot
with matching/anomaly classifications.

Design notes:
- Uses **tool use** to enforce JSON schema (Anthropic's recommended structured output).
- Uses **prompt caching** on the stable parts (system prompt + employee master + prev month)
  so a typical month with 100 clients × ~3 messages each pays only ~100 cache writes.
- The AI does NOT do final tax calc — that's deterministic in ``tax_calc.py`` post-parse.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from anthropic import AsyncAnthropic

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
    income_type: str = "WAGE"
    change_from_prev: int | None = None
    change_reason: str | None = None


@dataclass(slots=True)
class NewHireSuspected:
    name: str
    amount: int
    non_taxable: int = 0
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


# --- Prompt + tool definition ---------------------------------------------


_SYSTEM_PROMPT = """당신은 한국 세무사사무소의 원천세 자료 정형화 어시스턴트입니다.

[입력]
- 거래처(고객사)가 비정형 텍스트로 보낸 이번 달 인건비/지급액 자료
- 거래처의 직원 마스터(이름·식별자) 와 이전 달 지급액

[당신의 역할]
1. 본문에서 인명·금액·소득구분을 추출합니다.
2. 직원 마스터와 매칭합니다 (정확/유사/누락).
3. "저번 달이랑 똑같아요" 같은 상대 표현은 이전 달 데이터를 그대로 적용한 것으로 표시합니다.
4. 신규/퇴사 가능성을 분류합니다 — 결정은 사람에게 맡기고 당신은 의심자만 표시합니다.
5. 결과는 반드시 ``submit_payroll_parsing`` 도구 한 번 호출로만 반환합니다.

[규칙]
- 금액은 만원 단위 표기("100", "1.2백만") 도 정수 원 단위로 환산합니다 (100만원 → 1000000).
- 비과세소득이 명시되지 않으면 0.
- 소득구분이 명확하지 않으면 ``WAGE`` 로 둡니다.
- 추측한 부분은 ``ambiguous_items`` 에 함께 표시합니다.
- 직원 마스터에 없는 이름이 나오면 ``new_hire_suspected``.
- 마스터에는 있는데 이번 달 입력에서 빠진 직원은 ``resignation_suspected``.
- 동명이인이면 ``ambiguous_items`` 로.
"""

_TOOL_NAME = "submit_payroll_parsing"
_TOOL_SCHEMA: dict[str, Any] = {
    "name": _TOOL_NAME,
    "description": "이번 달 인건비 자료의 구조화 결과를 제출합니다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "matched_employees": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "employee_id": {"type": "string"},
                        "amount": {"type": "integer", "minimum": 0},
                        "non_taxable": {"type": "integer", "minimum": 0},
                        "income_type": {
                            "type": "string",
                            "enum": ["WAGE", "BUSINESS", "OTHER", "DAILY", "RETIREMENT"],
                        },
                        "change_from_prev": {"type": ["integer", "null"]},
                        "change_reason": {"type": ["string", "null"]},
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
                        "amount": {"type": "integer", "minimum": 0},
                        "non_taxable": {"type": "integer", "minimum": 0},
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
                        "note": {"type": ["string", "null"]},
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
    },
}


# --- Client interface (so tests can fake it) ------------------------------


class AnthropicLike(Protocol):
    @property
    def messages(self) -> Any: ...  # pragma: no cover


def _build_client() -> AsyncAnthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


# --- Main entry point -----------------------------------------------------


async def parse_payroll_message(
    raw_text: str,
    *,
    client_name: str,
    employee_master: list[dict[str, Any]],
    previous_month_data: list[dict[str, Any]],
    period: str,
    client: AnthropicLike | None = None,
    model: str | None = None,
) -> PayrollParsingResult:
    """Parse a raw client message into structured payroll data.

    Args:
        raw_text: 카톡/이메일/통화-STT 결과 등 비정형 텍스트.
        client_name: 거래처(사업자) 이름.
        employee_master: ``[{"id":..., "name":..., "last_amount":..., "last_paid_at":...}, ...]``
        previous_month_data: ``[{"name":..., "employee_id":..., "amount":...}, ...]``
        period: ``"YYYY-MM"`` (참고용 — 모델에 보여줌)
        client: 테스트용 Anthropic 클라이언트 주입 가능.
        model: 모델 ID 오버라이드.
    """
    settings = get_settings()
    client = client or _build_client()
    model = model or settings.anthropic_model

    # PII 가드: Claude API 외부 송신 전 주민번호·사업자번호·카드번호 마스킹.
    # 직원 마스터·이전월 데이터는 평문 객체에 RRN이 포함되지 않도록 호출자가 보장해야 하지만,
    # 방어적으로 재귀 마스킹을 한 번 더 수행.
    safe_text = redact_pii(raw_text)
    safe_master = redact_payload(employee_master)
    safe_prev = redact_payload(previous_month_data)

    stable_context = (
        f"[거래처] {client_name}\n"
        f"[직원 마스터]\n{json.dumps(safe_master, ensure_ascii=False, indent=2)}\n\n"
        f"[이전 달 데이터]\n{json.dumps(safe_prev, ensure_ascii=False, indent=2)}"
    )

    user_message = (
        f"[지급년월] {period}\n\n"
        f"[이번 달 메시지]\n{safe_text}\n\n"
        "위 메시지를 분석해 submit_payroll_parsing 도구를 호출하세요."
    )

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
        tools=[_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": stable_context,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {"type": "text", "text": user_message},
                ],
            }
        ],
    )

    return _parse_tool_response(response)


def _parse_tool_response(response: Any) -> PayrollParsingResult:
    tool_block = None
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == _TOOL_NAME:
            tool_block = block
            break

    if tool_block is None:
        logger.warning("AI parser: no tool_use block in response: %r", response)
        return PayrollParsingResult()

    data = tool_block.input or {}
    return PayrollParsingResult(
        matched_employees=[MatchedEmployee(**x) for x in data.get("matched_employees", [])],
        new_hire_suspected=[NewHireSuspected(**x) for x in data.get("new_hire_suspected", [])],
        resignation_suspected=[
            ResignationSuspected(**x) for x in data.get("resignation_suspected", [])
        ],
        ambiguous_items=[AmbiguousItem(**x) for x in data.get("ambiguous_items", [])],
        relative_references=[RelativeReference(**x) for x in data.get("relative_references", [])],
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
