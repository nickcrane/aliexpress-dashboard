"""Turns raw onboarding-wizard answers into a structured business plan via
Claude (claude-haiku-4-5). Uses a forced tool call with `strict: true`
rather than the newer output_config.format structured-outputs path --
tool use is the well-established, fully-documented way to get
schema-valid JSON back, and this is a one-shot extraction, not a
conversation, so no thinking/streaming is needed.

Cost: see dashboard/llm_usage.py for the monthly cap this feeds --
callers are expected to check is_over_cap() before calling
synthesize_business_plan and record_usage() after.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import anthropic

MODEL = "claude-haiku-4-5"

_SELLER_TYPES = ["content_creator", "dropship_store", "influencer", "existing_brand", "reseller", "other"]
_SALES_CHANNELS = ["own_website", "tiktok_shop", "instagram_shop", "etsy", "amazon", "in_person", "other"]
_MARKETING_APPROACHES = ["organic_content", "paid_ads", "influencer_partnerships", "seo", "email", "other"]
_BUDGET_STAGES = ["just_starting", "some_capital", "established"]

_SYSTEM_PROMPT = """\
You are helping a small e-commerce seller turn their answers to a short \
onboarding questionnaire into a structured business plan.

Call submit_business_plan exactly once with your extraction. Rules:
- Only use information the user actually gave you -- never invent details.
- Leave a field null if the user's answers don't clearly cover it. Don't
  guess just to fill every field.
- primary_category_name must be exactly one of the provided category
  names, chosen as the best match for their product niche -- or null if
  none fit reasonably.
- summary is always required: 2-3 plain-English sentences describing
  their business back to them, written so they can quickly confirm it's
  right (not a restatement of the raw answers).
- Never give financial, legal, or tax advice.
"""


@dataclass
class SynthesizedPlan:
    seller_type: Optional[str]
    product_niche: Optional[str]
    target_market: Optional[str]
    sales_channels: List[str] = field(default_factory=list)
    marketing_approach: List[str] = field(default_factory=list)
    budget_stage: Optional[str] = None
    primary_category_id: Optional[int] = None
    summary: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


def _build_tool(category_names: List[str]) -> dict:
    return {
        "name": "submit_business_plan",
        "description": "Record the structured business plan extracted from the user's onboarding answers.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "seller_type": {"type": ["string", "null"], "enum": _SELLER_TYPES + [None]},
                "product_niche": {"type": ["string", "null"]},
                "target_market": {"type": ["string", "null"]},
                "sales_channels": {"type": "array", "items": {"type": "string", "enum": _SALES_CHANNELS}},
                "marketing_approach": {"type": "array", "items": {"type": "string", "enum": _MARKETING_APPROACHES}},
                "budget_stage": {"type": ["string", "null"], "enum": _BUDGET_STAGES + [None]},
                "primary_category_name": {"type": ["string", "null"], "enum": category_names + [None]},
                "summary": {"type": "string"},
            },
            "required": [
                "seller_type",
                "product_niche",
                "target_market",
                "sales_channels",
                "marketing_approach",
                "budget_stage",
                "primary_category_name",
                "summary",
            ],
            "additionalProperties": False,
        },
    }


def _format_answers(wizard_answers: dict) -> str:
    lines = [f"{question}: {answer}" for question, answer in wizard_answers.items() if answer]
    return "Onboarding answers:\n" + "\n".join(lines) if lines else "The user skipped every question."


async def synthesize_business_plan(
    *,
    api_key: str = "",
    client: Optional[anthropic.AsyncAnthropic] = None,
    wizard_answers: dict,
    categories: List[Tuple[int, str]],
) -> SynthesizedPlan:
    """categories: (category_id, category_name) pairs for the top-level
    categories to choose primary_category_name from -- pass
    dashboard.queries.category_tree()'s parent nodes.

    Async (AsyncAnthropic) because the only caller is spa/app.py's
    onboarding route, which is async like every other route there (it
    awaits an httpx.AsyncClient proxy call) -- a blocking SDK call would
    stall that event loop for the whole request.

    `client` is injectable so tests can pass a stub instead of hitting
    the real API; production callers pass `api_key` and let this build
    the real client."""
    name_to_id = {name: category_id for category_id, name in categories}
    client = client or anthropic.AsyncAnthropic(api_key=api_key)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        tools=[_build_tool(list(name_to_id.keys()))],
        tool_choice={"type": "tool", "name": "submit_business_plan"},
        messages=[{"role": "user", "content": _format_answers(wizard_answers)}],
    )

    tool_use = next(block for block in response.content if block.type == "tool_use")
    plan = tool_use.input

    return SynthesizedPlan(
        seller_type=plan.get("seller_type"),
        product_niche=plan.get("product_niche"),
        target_market=plan.get("target_market"),
        sales_channels=plan.get("sales_channels") or [],
        marketing_approach=plan.get("marketing_approach") or [],
        budget_stage=plan.get("budget_stage"),
        primary_category_id=name_to_id.get(plan.get("primary_category_name")),
        summary=plan.get("summary") or "",
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
