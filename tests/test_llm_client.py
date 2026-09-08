"""Unit tests for llm_client.py using a stub Anthropic client -- no real
API key or network call needed, matching how test_ali_client.py stays
offline via fixtures. The stub mimics just enough of the real SDK's
response shape (content blocks, usage) to exercise the parsing logic."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, List

from aliexpress_dashboard.client.llm_client import synthesize_business_plan

# No pytest-asyncio in this project (everything else is sync) -- run the
# one async entry point synchronously rather than add a plugin for it.
_run = asyncio.run


@dataclass
class _StubToolUseBlock:
    input: dict
    type: str = "tool_use"


@dataclass
class _StubUsage:
    input_tokens: int
    output_tokens: int


@dataclass
class _StubMessage:
    content: List[Any]
    usage: _StubUsage


class _StubMessagesResource:
    def __init__(self, response: _StubMessage, *, capture: dict) -> None:
        self._response = response
        self._capture = capture

    async def create(self, **kwargs):
        self._capture.update(kwargs)
        return self._response


class _StubAnthropicClient:
    def __init__(self, response: _StubMessage) -> None:
        self.calls: dict = {}
        self.messages = _StubMessagesResource(response, capture=self.calls)


CATEGORIES = [(44, "Consumer Electronics"), (1420, "Tools")]


def _stub_client(plan_input: dict, *, input_tokens=500, output_tokens=150) -> _StubAnthropicClient:
    response = _StubMessage(
        content=[_StubToolUseBlock(input=plan_input)],
        usage=_StubUsage(input_tokens=input_tokens, output_tokens=output_tokens),
    )
    return _StubAnthropicClient(response)


def test_synthesize_maps_full_plan():
    stub = _stub_client(
        {
            "seller_type": "content_creator",
            "product_niche": "kitchen gadgets",
            "target_market": "young home cooks",
            "sales_channels": ["tiktok_shop"],
            "marketing_approach": ["organic_content"],
            "budget_stage": "just_starting",
            "primary_category_name": "Tools",
            "summary": "A content creator selling kitchen gadgets via TikTok Shop.",
        }
    )
    plan = _run(
        synthesize_business_plan(client=stub, wizard_answers={"niche": "kitchen gadgets"}, categories=CATEGORIES)
    )

    assert plan.seller_type == "content_creator"
    assert plan.product_niche == "kitchen gadgets"
    assert plan.sales_channels == ["tiktok_shop"]
    assert plan.primary_category_id == 1420
    assert plan.summary.startswith("A content creator")
    assert plan.input_tokens == 500
    assert plan.output_tokens == 150


def test_synthesize_handles_null_fields():
    stub = _stub_client(
        {
            "seller_type": None,
            "product_niche": None,
            "target_market": None,
            "sales_channels": [],
            "marketing_approach": [],
            "budget_stage": None,
            "primary_category_name": None,
            "summary": "Not enough information was given to build a plan yet.",
        }
    )
    plan = _run(synthesize_business_plan(client=stub, wizard_answers={}, categories=CATEGORIES))

    assert plan.seller_type is None
    assert plan.primary_category_id is None
    assert plan.sales_channels == []


def test_synthesize_sends_forced_tool_choice_and_category_names():
    stub = _stub_client({"summary": "x", "sales_channels": [], "marketing_approach": []})
    _run(synthesize_business_plan(client=stub, wizard_answers={"a": "b"}, categories=CATEGORIES))

    assert stub.calls["tool_choice"] == {"type": "tool", "name": "submit_business_plan"}
    tool = stub.calls["tools"][0]
    assert tool["strict"] is True
    category_enum = tool["input_schema"]["properties"]["primary_category_name"]["enum"]
    assert "Consumer Electronics" in category_enum
    assert "Tools" in category_enum


def test_format_answers_skips_empty_values():
    from aliexpress_dashboard.client.llm_client import _format_answers

    text = _format_answers({"niche": "kitchen gadgets", "target_market": "", "budget": None})
    assert "kitchen gadgets" in text
    assert "target_market" not in text
    assert "budget" not in text


def test_format_answers_all_skipped():
    from aliexpress_dashboard.client.llm_client import _format_answers

    assert _format_answers({}) == "The user skipped every question."
