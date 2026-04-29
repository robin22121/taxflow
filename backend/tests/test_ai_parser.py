"""AI parser tests using a fake Anthropic client.

We do NOT hit the live API in tests — instead we inject a stub client whose
``messages.create`` returns a canned response shaped like the SDK output.
"""

from types import SimpleNamespace

import pytest

from app.services.ai_parser import (
    PayrollParsingResult,
    parse_payroll_message,
)


class _FakeAnthropic:
    def __init__(self, tool_input: dict):
        self._tool_input = tool_input
        self.messages = self  # so client.messages.create works
        self.create_calls: list[dict] = []

    async def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return SimpleNamespace(
            content=[
                SimpleNamespace(
                    type="tool_use",
                    name="submit_payroll_parsing",
                    input=self._tool_input,
                )
            ]
        )


@pytest.mark.asyncio
async def test_basic_parse():
    fake = _FakeAnthropic(
        {
            "matched_employees": [
                {
                    "name": "김연호",
                    "employee_id": "e1",
                    "amount": 1_000_000,
                    "non_taxable": 0,
                    "income_type": "WAGE",
                    "change_from_prev": 0,
                    "change_reason": None,
                },
                {
                    "name": "조명신",
                    "employee_id": "e2",
                    "amount": 1_200_000,
                    "non_taxable": 0,
                    "income_type": "WAGE",
                    "change_from_prev": 200_000,
                    "change_reason": "보너스",
                },
            ],
            "new_hire_suspected": [],
            "resignation_suspected": [],
            "ambiguous_items": [],
            "relative_references": [],
        }
    )
    res = await parse_payroll_message(
        raw_text="김연호 100, 조명신 120 (보너스 20 포함)",
        client_name="A상사",
        employee_master=[
            {"id": "e1", "name": "김연호", "last_amount": 1_000_000},
            {"id": "e2", "name": "조명신", "last_amount": 1_000_000},
        ],
        previous_month_data=[
            {"name": "김연호", "employee_id": "e1", "amount": 1_000_000},
            {"name": "조명신", "employee_id": "e2", "amount": 1_000_000},
        ],
        period="2026-04",
        client=fake,
    )
    assert isinstance(res, PayrollParsingResult)
    assert len(res.matched_employees) == 2
    assert res.matched_employees[0].name == "김연호"
    assert res.matched_employees[1].change_from_prev == 200_000


@pytest.mark.asyncio
async def test_uses_prompt_caching_and_tool_choice():
    fake = _FakeAnthropic(
        {
            "matched_employees": [],
            "new_hire_suspected": [],
            "resignation_suspected": [],
            "ambiguous_items": [],
            "relative_references": [],
        }
    )
    await parse_payroll_message(
        raw_text="hi",
        client_name="A상사",
        employee_master=[],
        previous_month_data=[],
        period="2026-04",
        client=fake,
    )
    call = fake.create_calls[0]
    # System has cache_control
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    # Stable context has cache_control
    assert call["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    # Tool choice forces our tool
    assert call["tool_choice"] == {"type": "tool", "name": "submit_payroll_parsing"}


@pytest.mark.asyncio
async def test_redacts_rrn_before_calling_claude():
    """주민번호가 메시지에 섞여 있으면 Claude로 가는 페이로드에서 마스킹되어야 한다."""
    fake = _FakeAnthropic(
        {
            "matched_employees": [],
            "new_hire_suspected": [],
            "resignation_suspected": [],
            "ambiguous_items": [],
            "relative_references": [],
        }
    )
    await parse_payroll_message(
        raw_text="신규 박민수 900101-1234567 150만원, 사업자 111-22-33333",
        client_name="A상사",
        employee_master=[],
        previous_month_data=[],
        period="2026-04",
        client=fake,
    )
    sent = fake.create_calls[0]["messages"][0]["content"][1]["text"]
    assert "900101-1234567" not in sent
    assert "111-22-33333" not in sent
    # Marker pattern still present so we can see it was an RRN
    assert "******-*******" in sent


@pytest.mark.asyncio
async def test_handles_no_tool_use_block():
    class FakeNoTool:
        messages = property(lambda self: self)

        async def create(self, **kw):
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="oops")])

    res = await parse_payroll_message(
        raw_text="x",
        client_name="A",
        employee_master=[],
        previous_month_data=[],
        period="2026-04",
        client=FakeNoTool(),
    )
    # Falls back to empty result rather than raising
    assert res.matched_employees == []
    assert res.raw_response is None


@pytest.mark.asyncio
async def test_resignation_and_new_hire_classification():
    fake = _FakeAnthropic(
        {
            "matched_employees": [
                {"name": "김연호", "employee_id": "e1", "amount": 1_000_000},
            ],
            "new_hire_suspected": [
                {"name": "박민수", "amount": 1_500_000, "needs_confirmation": True},
            ],
            "resignation_suspected": [
                {"employee_id": "e3", "name": "이영수", "reason": "이번달 누락"},
            ],
            "ambiguous_items": [],
            "relative_references": [
                {"text": "저번달과 동일", "applied": True, "note": None},
            ],
        }
    )
    res = await parse_payroll_message(
        raw_text="김연호 100, 박민수 신규 150, 이영수는 빠짐",
        client_name="A상사",
        employee_master=[
            {"id": "e1", "name": "김연호"},
            {"id": "e3", "name": "이영수"},
        ],
        previous_month_data=[
            {"name": "김연호", "employee_id": "e1", "amount": 1_000_000},
            {"name": "이영수", "employee_id": "e3", "amount": 1_500_000},
        ],
        period="2026-04",
        client=fake,
    )
    assert len(res.new_hire_suspected) == 1
    assert res.new_hire_suspected[0].name == "박민수"
    assert len(res.resignation_suspected) == 1
    assert res.resignation_suspected[0].employee_id == "e3"
    assert res.relative_references[0].applied is True
