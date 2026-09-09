"""Turns raw onboarding-wizard answers into a structured business plan via
Claude (claude-haiku-4-5). Uses a forced tool call with `strict: true`
rather than the newer output_config.format structured-outputs path --
tool use is the well-established, fully-documented way to get
schema-valid JSON back, and this is a one-shot extraction, not a
conversation, so no thinking/streaming is needed.

primary_category_id is deliberately NOT something this asks the LLM to
infer -- confirmed live that asking it to match free-text product_niche
against a list of category names frequently returned null even for a
clear case ("kitchen gadgets" against a list including "Home & Garden"),
silently breaking the Products page defaults for anyone that happened
to. The wizard now has the user pick a category directly from
dashboard.queries.category_tree()'s real parent list (Material Web
chips, deterministic, always a valid id) instead -- see spa/app.py's
onboarding route, which passes it straight through.

Cost: see dashboard/llm_usage.py for the monthly cap this feeds --
callers are expected to check is_over_cap() before calling
synthesize_business_plan and record_usage() after.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

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
- summary is always required: 2-3 plain-English sentences describing
  their business back to them, written so they can quickly confirm it's
  right (not a restatement of the raw answers).
- market_gap_analysis: if category market stats are provided below, write
  3-5 plain-English sentences pointing out a concrete opportunity or risk
  grounded ONLY in those numbers -- e.g. a price band with strong demand
  (high median sales volume) but few listings, or a saturated band to
  avoid. Never invent competitor names, market-size figures, or numbers
  not present in the supplied stats. If no stats are provided, set this
  field to null -- don't write a generic answer.
- Never give financial, legal, or tax advice.
"""

_TOOL = {
    "name": "submit_business_plan",
    "description": "Record the structured business plan extracted from the user's onboarding answers.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "seller_type": {"anyOf": [{"type": "string", "enum": _SELLER_TYPES}, {"type": "null"}]},
            "product_niche": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "target_market": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "sales_channels": {"type": "array", "items": {"type": "string", "enum": _SALES_CHANNELS}},
            "marketing_approach": {"type": "array", "items": {"type": "string", "enum": _MARKETING_APPROACHES}},
            "budget_stage": {"anyOf": [{"type": "string", "enum": _BUDGET_STAGES}, {"type": "null"}]},
            "summary": {"type": "string"},
            "market_gap_analysis": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
        "required": [
            "seller_type",
            "product_niche",
            "target_market",
            "sales_channels",
            "marketing_approach",
            "budget_stage",
            "summary",
            "market_gap_analysis",
        ],
        "additionalProperties": False,
    },
}


@dataclass
class SynthesizedPlan:
    seller_type: Optional[str]
    product_niche: Optional[str]
    target_market: Optional[str]
    sales_channels: List[str] = field(default_factory=list)
    marketing_approach: List[str] = field(default_factory=list)
    budget_stage: Optional[str] = None
    summary: str = ""
    market_gap_analysis: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0


def _format_answers(wizard_answers: dict) -> str:
    lines = [f"{question}: {answer}" for question, answer in wizard_answers.items() if answer]
    return "Onboarding answers:\n" + "\n".join(lines) if lines else "The user skipped every question."


def _format_market_stats(market_stats: Optional[dict]) -> str:
    """Renders dashboard.queries.category_market_stats's output into a
    plain-text block for the prompt -- kept separate from the numbers
    themselves so the LLM only ever sees real, already-computed stats,
    never raw product rows it could over-interpret or hallucinate from."""
    if not market_stats or not market_stats.get("product_count"):
        return "No category market stats are available."

    currency = market_stats.get("price_currency") or ""
    lines = [f"Category market stats ({market_stats['product_count']} currently tracked listings):"]
    if market_stats.get("price_min") is not None:
        lines.append(
            f"- Price range: {market_stats['price_min']}-{market_stats['price_max']} {currency} "
            f"(median {market_stats['price_median']})"
        )
    if market_stats.get("avg_positive_feedback_pct") is not None:
        lines.append(f"- Average positive-feedback score: {market_stats['avg_positive_feedback_pct']}%")
    if market_stats.get("avg_discount_pct") is not None:
        lines.append(f"- Average listed discount: {market_stats['avg_discount_pct']}%")
    if market_stats.get("median_sales_volume") is not None:
        lines.append(f"- Median sales volume per listing: {market_stats['median_sales_volume']}")
    if market_stats.get("price_bands"):
        lines.append("- Price bands (listing count, avg feedback %, median sales volume):")
        for band in market_stats["price_bands"]:
            lines.append(
                f"  - {band['price_low']}-{band['price_high']} {currency}: "
                f"{band['product_count']} listings, "
                f"{band['avg_positive_feedback_pct']}% avg feedback, "
                f"{band['median_sales_volume']} median sales volume"
            )
    return "\n".join(lines)


async def synthesize_business_plan(
    *,
    api_key: str = "",
    client: Optional[anthropic.AsyncAnthropic] = None,
    wizard_answers: dict,
    market_stats: Optional[dict] = None,
) -> SynthesizedPlan:
    """Async (AsyncAnthropic) because the only caller is spa/app.py's
    onboarding route, which is async like every other route there (it
    awaits an httpx.AsyncClient proxy call) -- a blocking SDK call would
    stall that event loop for the whole request.

    `client` is injectable so tests can pass a stub instead of hitting
    the real API; production callers pass `api_key` and let this build
    the real client. `market_stats` is dashboard.queries.category_market_stats's
    output for the category the user picked in the wizard (or None if
    they didn't pick one / nothing's been collected for it yet) -- feeds
    the market_gap_analysis field."""
    client = client or anthropic.AsyncAnthropic(api_key=api_key)

    user_content = _format_answers(wizard_answers) + "\n\n" + _format_market_stats(market_stats)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        tools=[_TOOL],
        tool_choice={"type": "tool", "name": "submit_business_plan"},
        messages=[{"role": "user", "content": user_content}],
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
        summary=plan.get("summary") or "",
        market_gap_analysis=plan.get("market_gap_analysis"),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
