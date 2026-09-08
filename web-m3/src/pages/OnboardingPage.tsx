import "@material/web/textfield/outlined-text-field.js";
import "@material/web/button/filled-button.js";
import "@material/web/button/outlined-button.js";
import "@material/web/button/text-button.js";

import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api";
import type { BusinessProfile } from "../types";

// Chip-style single/multi-select built from plain buttons rather than
// md-filter-chip: this app has an already-verified pattern for buttons
// (onClick works directly, unlike md-outlined-select's value/onchange,
// which needed the lowercase-event workaround) -- filter-chip's
// `selected` boolean property reflecting correctly via JSX is untested
// here, so this avoids guessing at an unfamiliar component's behavior.
function ChoiceButton({
  label,
  selected,
  onClick,
}: {
  label: string;
  selected: boolean;
  onClick: () => void;
}) {
  const Tag = selected ? "md-filled-button" : "md-outlined-button";
  return (
    <Tag type="button" onClick={onClick}>
      {label}
    </Tag>
  );
}

const SELLER_TYPES: [string, string][] = [
  ["content_creator", "Content creator"],
  ["dropship_store", "Dropship store"],
  ["influencer", "Influencer"],
  ["existing_brand", "Existing brand"],
  ["reseller", "Reseller"],
  ["other", "Other"],
];

const SALES_CHANNELS: [string, string][] = [
  ["own_website", "Own website"],
  ["tiktok_shop", "TikTok Shop"],
  ["instagram_shop", "Instagram Shop"],
  ["etsy", "Etsy"],
  ["amazon", "Amazon"],
  ["in_person", "In person"],
  ["other", "Other"],
];

const MARKETING_APPROACHES: [string, string][] = [
  ["organic_content", "Organic content"],
  ["paid_ads", "Paid ads"],
  ["influencer_partnerships", "Influencer partnerships"],
  ["seo", "SEO"],
  ["email", "Email"],
  ["other", "Other"],
];

const BUDGET_STAGES: [string, string][] = [
  ["just_starting", "Just starting out"],
  ["some_capital", "Some capital to invest"],
  ["established", "Established business"],
];

function ChoiceRow({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: [string, string][];
  selected: Set<string>;
  onToggle: (value: string) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <span style={{ fontSize: "0.9rem", fontWeight: 500 }}>{label}</span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        {options.map(([value, text]) => (
          <ChoiceButton key={value} label={text} selected={selected.has(value)} onClick={() => onToggle(value)} />
        ))}
      </div>
    </div>
  );
}

export function OnboardingPage() {
  const navigate = useNavigate();
  const [sellerType, setSellerType] = useState<string | null>(null);
  const [productNiche, setProductNiche] = useState("");
  const [targetMarket, setTargetMarket] = useState("");
  const [salesChannels, setSalesChannels] = useState<Set<string>>(new Set());
  const [marketingApproach, setMarketingApproach] = useState<Set<string>>(new Set());
  const [budgetStage, setBudgetStage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BusinessProfile | null>(null);

  function toggleInSet(set: Set<string>, setter: (s: Set<string>) => void, value: string) {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    setter(next);
  }

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    const seller_type_label = SELLER_TYPES.find(([v]) => v === sellerType)?.[1] ?? "";
    const budget_stage_label = BUDGET_STAGES.find(([v]) => v === budgetStage)?.[1] ?? "";
    try {
      const profile = await api.synthesizeOnboarding({
        seller_type: seller_type_label,
        product_niche: productNiche,
        target_market: targetMarket,
        sales_channels: [...salesChannels]
          .map((v) => SALES_CHANNELS.find(([value]) => value === v)?.[1])
          .filter(Boolean)
          .join(", "),
        marketing_approach: [...marketingApproach]
          .map((v) => MARKETING_APPROACHES.find(([value]) => value === v)?.[1])
          .filter(Boolean)
          .join(", "),
        budget_stage: budget_stage_label,
      });
      setResult(profile);
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  if (result) {
    return (
      <div style={{ maxWidth: "32rem", margin: "0 auto", padding: "1.5rem 1rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <h1 style={{ fontSize: "1.3rem" }}>Here's your business plan</h1>
        <p>{result.summary}</p>
        <div style={{ fontSize: "0.85rem", color: "var(--md-sys-color-on-surface-variant)", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          {result.seller_type && <div>Seller type: {result.seller_type}</div>}
          {result.product_niche && <div>Niche: {result.product_niche}</div>}
          {result.target_market && <div>Target market: {result.target_market}</div>}
          {result.sales_channels.length > 0 && <div>Sales channels: {result.sales_channels.join(", ")}</div>}
          {result.marketing_approach.length > 0 && <div>Marketing: {result.marketing_approach.join(", ")}</div>}
        </div>
        <md-filled-button type="button" onClick={() => navigate("/")}>
          Go to products
        </md-filled-button>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: "32rem", margin: "0 auto", padding: "1.5rem 1rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div>
        <h1 style={{ fontSize: "1.3rem", marginBottom: "0.25rem" }}>Tell us about your business</h1>
        <p style={{ fontSize: "0.85rem", color: "var(--md-sys-color-on-surface-variant)", margin: 0 }}>
          A few quick questions -- skip anything that doesn't apply. We'll use this to suggest a starting point,
          which you can always change or clear later.
        </p>
      </div>

      <ChoiceRow label="What kind of seller are you?" options={SELLER_TYPES} selected={sellerType ? new Set([sellerType]) : new Set()} onToggle={(v) => setSellerType(sellerType === v ? null : v)} />

      <md-outlined-text-field
        label="What products are you interested in selling?"
        value={productNiche}
        oninput={(e: Event) => setProductNiche((e.target as HTMLInputElement).value)}
      />

      <md-outlined-text-field
        label="Who are you selling to?"
        value={targetMarket}
        oninput={(e: Event) => setTargetMarket((e.target as HTMLInputElement).value)}
      />

      <ChoiceRow
        label="Where do you plan to sell?"
        options={SALES_CHANNELS}
        selected={salesChannels}
        onToggle={(v) => toggleInSet(salesChannels, setSalesChannels, v)}
      />

      <ChoiceRow
        label="How do you plan to market?"
        options={MARKETING_APPROACHES}
        selected={marketingApproach}
        onToggle={(v) => toggleInSet(marketingApproach, setMarketingApproach, v)}
      />

      <ChoiceRow label="What stage are you at?" options={BUDGET_STAGES} selected={budgetStage ? new Set([budgetStage]) : new Set()} onToggle={(v) => setBudgetStage(budgetStage === v ? null : v)} />

      {error && <div style={{ color: "var(--md-sys-color-error)" }}>{error}</div>}

      <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
        <md-filled-button type="button" disabled={submitting} onClick={handleSubmit}>
          {submitting ? "Building your plan..." : "Build my plan"}
        </md-filled-button>
        <md-text-button type="button" disabled={submitting} onClick={() => navigate("/")}>
          Skip for now
        </md-text-button>
      </div>
    </div>
  );
}
