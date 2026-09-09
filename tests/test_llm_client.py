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
            "summary": "A content creator selling kitchen gadgets via TikTok Shop.",
            "market_gap_analysis": "The $10-15 band has strong demand but few listings.",
            "tiktok_shop_angle": "Compact kitchen gadgets demo well in quick before/after clips.",
        }
    )
    plan = _run(synthesize_business_plan(client=stub, wizard_answers={"niche": "kitchen gadgets"}))

    assert plan.seller_type == "content_creator"
    assert plan.product_niche == "kitchen gadgets"
    assert plan.sales_channels == ["tiktok_shop"]
    assert plan.summary.startswith("A content creator")
    assert plan.market_gap_analysis == "The $10-15 band has strong demand but few listings."
    assert plan.tiktok_shop_angle == "Compact kitchen gadgets demo well in quick before/after clips."
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
            "summary": "Not enough information was given to build a plan yet.",
        }
    )
    plan = _run(synthesize_business_plan(client=stub, wizard_answers={}))

    assert plan.seller_type is None
    assert plan.sales_channels == []


def test_synthesize_sends_forced_tool_choice():
    stub = _stub_client({"summary": "x", "sales_channels": [], "marketing_approach": []})
    _run(synthesize_business_plan(client=stub, wizard_answers={"a": "b"}))

    assert stub.calls["tool_choice"] == {"type": "tool", "name": "submit_business_plan"}
    tool = stub.calls["tools"][0]
    assert tool["strict"] is True
    assert "primary_category_name" not in tool["input_schema"]["properties"]
    assert "market_gap_analysis" in tool["input_schema"]["properties"]
    assert "market_gap_analysis" in tool["input_schema"]["required"]
    assert "tiktok_shop_angle" in tool["input_schema"]["properties"]
    assert "tiktok_shop_angle" in tool["input_schema"]["required"]
    # Nullable fields are anyOf: [{type: string, ...}, {type: null}] --
    # confirmed live that the plain type:["string","null"] shorthand is
    # rejected by Anthropic's strict schema validator.
    seller_type_field = tool["input_schema"]["properties"]["seller_type"]
    assert seller_type_field["anyOf"][1] == {"type": "null"}


def test_synthesize_includes_market_stats_in_prompt():
    stub = _stub_client({"summary": "x", "sales_channels": [], "marketing_approach": []})
    market_stats = {
        "category_id": 15,
        "product_count": 2,
        "price_currency": "GBP",
        "price_min": 2.49,
        "price_median": 6.24,
        "price_max": 9.99,
        "avg_discount_pct": 42.5,
        "avg_positive_feedback_pct": 94.5,
        "median_sales_volume": 7617,
        "price_bands": [
            {"price_low": 2.49, "price_high": 6.24, "product_count": 1, "avg_positive_feedback_pct": None,
             "median_sales_volume": 0},
        ],
    }
    _run(synthesize_business_plan(client=stub, wizard_answers={}, market_stats=market_stats))

    user_message = stub.calls["messages"][0]["content"]
    assert "2 currently tracked listings" in user_message
    assert "2.49-9.99 GBP" in user_message
    assert "94.5%" in user_message


def test_synthesize_without_market_stats_says_none_available():
    stub = _stub_client({"summary": "x", "sales_channels": [], "marketing_approach": []})
    _run(synthesize_business_plan(client=stub, wizard_answers={}))

    assert "No category market stats are available." in stub.calls["messages"][0]["content"]


def test_system_prompt_bars_fabricated_tiktok_success_stories():
    # Regression guard: this is the one field this app asks the LLM to
    # write from general knowledge rather than supplied data (no real
    # TikTok Shop data source is integrated -- see llm_client module
    # docstring/session notes), so the instruction not to name real
    # companies/creators or invent figures is load-bearing. Cheap text
    # check rather than a live-model assertion.
    from aliexpress_dashboard.client.llm_client import _SYSTEM_PROMPT

    normalized = " ".join(_SYSTEM_PROMPT.split())
    assert "NEVER name a real company, creator, or product" in normalized
    assert "specific sales, revenue, or follower figure as fact" in normalized


def test_format_answers_skips_empty_values():
    from aliexpress_dashboard.client.llm_client import _format_answers

    text = _format_answers({"niche": "kitchen gadgets", "target_market": "", "budget": None})
    assert "kitchen gadgets" in text
    assert "target_market" not in text
    assert "budget" not in text


def test_format_answers_all_skipped():
    from aliexpress_dashboard.client.llm_client import _format_answers

    assert _format_answers({}) == "The user skipped every question."


def test_format_market_stats_none():
    from aliexpress_dashboard.client.llm_client import _format_market_stats

    assert _format_market_stats(None) == "No category market stats are available."
    assert _format_market_stats({"category_id": 15, "product_count": 0}) == "No category market stats are available."


def test_format_market_stats_renders_bands():
    from aliexpress_dashboard.client.llm_client import _format_market_stats

    text = _format_market_stats(
        {
            "category_id": 15,
            "product_count": 2,
            "price_currency": "GBP",
            "price_min": 2.49,
            "price_median": 6.24,
            "price_max": 9.99,
            "avg_discount_pct": 42.5,
            "avg_positive_feedback_pct": 94.5,
            "median_sales_volume": 7617,
            "price_bands": [
                {
                    "price_low": 2.49,
                    "price_high": 6.24,
                    "product_count": 1,
                    "avg_positive_feedback_pct": None,
                    "median_sales_volume": 0,
                }
            ],
        }
    )
    assert "2 currently tracked listings" in text
    assert "2.49-9.99 GBP" in text
    assert "42.5%" in text
    assert "2.49-6.24 GBP: 1 listings" in text
