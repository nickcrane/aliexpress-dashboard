import "@material/web/textfield/outlined-text-field.js";
import "@material/web/button/filled-button.js";
import "@material/web/button/outlined-button.js";
import "@material/web/button/text-button.js";

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api";
import type { BusinessProfile, CategoryTreeNode } from "../types";

// Chip-style single/multi-select built from plain buttons rather than
// md-filter-chip: this app has an already-verified pattern for buttons
// (onClick works directly, unlike md-outlined-select's value/onchange,
// which needed the lowercase-event workaround) -- filter-chip's
// `selected` boolean property reflecting correctly via JSX is untested
// here, so this avoids guessing at an unfamiliar component's behavior.
function ChoiceButton({ label, selected, onClick }: { label: string; selected: boolean; onClick: () => void }) {
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

interface WizardFormProps {
  initialProfile: BusinessProfile | null;
  categoryTree: CategoryTreeNode[];
  onSubmit: (fields: Record<string, string>, primaryCategoryId: number | null) => Promise<void>;
  onCancel: (() => void) | null;
}

function WizardForm({ initialProfile, categoryTree, onSubmit, onCancel }: WizardFormProps) {
  const [sellerType, setSellerType] = useState<string | null>(initialProfile?.seller_type ?? null);
  const [productNiche, setProductNiche] = useState(initialProfile?.product_niche ?? "");
  const [targetMarket, setTargetMarket] = useState(initialProfile?.target_market ?? "");
  const [primaryCategoryId, setPrimaryCategoryId] = useState<number | null>(
    initialProfile?.primary_category_id ?? null,
  );
  const [salesChannels, setSalesChannels] = useState<Set<string>>(new Set(initialProfile?.sales_channels ?? []));
  const [marketingApproach, setMarketingApproach] = useState<Set<string>>(
    new Set(initialProfile?.marketing_approach ?? []),
  );
  const [budgetStage, setBudgetStage] = useState<string | null>(initialProfile?.budget_stage ?? null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Parent categories only ("parent product descriptions" per the ask) --
  // these are real, already-synced categories with products under them
  // (dashboard.queries.category_tree), so picking one here can never
  // produce an id the Products page filter won't recognize -- unlike the
  // LLM's free-text category-name guess this replaces.
  const categoryOptions: [string, string][] = categoryTree.map((node) => [
    String(node.category_id),
    node.category_name,
  ]);

  function toggleInSet(set: Set<string>, setter: (s: Set<string>) => void, value: string) {
    const next = new Set(set);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    setter(next);
  }

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(
        {
          seller_type: SELLER_TYPES.find(([v]) => v === sellerType)?.[1] ?? "",
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
          budget_stage: BUDGET_STAGES.find(([v]) => v === budgetStage)?.[1] ?? "",
        },
        primaryCategoryId,
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <ChoiceRow
        label="What kind of seller are you?"
        options={SELLER_TYPES}
        selected={sellerType ? new Set([sellerType]) : new Set()}
        onToggle={(v) => setSellerType(sellerType === v ? null : v)}
      />

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

      {categoryOptions.length > 0 && (
        <ChoiceRow
          label="Which product category fits best?"
          options={categoryOptions}
          selected={primaryCategoryId !== null ? new Set([String(primaryCategoryId)]) : new Set()}
          onToggle={(v) => setPrimaryCategoryId(primaryCategoryId === Number(v) ? null : Number(v))}
        />
      )}

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

      <ChoiceRow
        label="What stage are you at?"
        options={BUDGET_STAGES}
        selected={budgetStage ? new Set([budgetStage]) : new Set()}
        onToggle={(v) => setBudgetStage(budgetStage === v ? null : v)}
      />

      {error && <div style={{ color: "var(--md-sys-color-error)" }}>{error}</div>}

      <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
        <md-filled-button type="button" disabled={submitting} onClick={handleSubmit}>
          {submitting ? "Building your plan..." : initialProfile ? "Save changes" : "Build my plan"}
        </md-filled-button>
        {onCancel && (
          <md-text-button type="button" disabled={submitting} onClick={onCancel}>
            Cancel
          </md-text-button>
        )}
      </div>
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

function PlanView({
  activeProfile,
  versions,
  categoryTree,
  onEdit,
  onNew,
  onActivate,
  onDelete,
}: {
  activeProfile: BusinessProfile;
  versions: BusinessProfile[];
  categoryTree: CategoryTreeNode[];
  onEdit: () => void;
  onNew: () => void;
  onActivate: (id: number) => void;
  onDelete: (id: number) => void;
}) {
  const otherVersions = versions.filter((v) => v.id !== activeProfile.id);
  const categoryName = categoryTree.find((node) => node.category_id === activeProfile.primary_category_id)
    ?.category_name;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div>
        <h1 style={{ fontSize: "1.3rem", marginBottom: "0.5rem" }}>Your business plan</h1>
        <p>{activeProfile.summary}</p>
        <div
          style={{
            fontSize: "0.85rem",
            color: "var(--md-sys-color-on-surface-variant)",
            display: "flex",
            flexDirection: "column",
            gap: "0.25rem",
          }}
        >
          {activeProfile.seller_type && <div>Seller type: {activeProfile.seller_type}</div>}
          {activeProfile.product_niche && <div>Niche: {activeProfile.product_niche}</div>}
          {categoryName && <div>Category: {categoryName}</div>}
          {activeProfile.target_market && <div>Target market: {activeProfile.target_market}</div>}
          {activeProfile.sales_channels.length > 0 && (
            <div>Sales channels: {activeProfile.sales_channels.join(", ")}</div>
          )}
          {activeProfile.marketing_approach.length > 0 && (
            <div>Marketing: {activeProfile.marketing_approach.join(", ")}</div>
          )}
        </div>
      </div>

      <div style={{ display: "flex", gap: "0.75rem" }}>
        <md-filled-button type="button" onClick={onEdit}>
          Edit this plan
        </md-filled-button>
        <md-outlined-button type="button" onClick={onNew}>
          Create new version
        </md-outlined-button>
      </div>

      {otherVersions.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          <h2 style={{ fontSize: "1rem", margin: 0 }}>Other versions</h2>
          {otherVersions.map((version) => (
            <div
              key={version.id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: "0.75rem",
                background: "var(--md-sys-color-surface-container-low)",
                padding: "0.6rem 0.85rem",
                borderRadius: "var(--md-sys-shape-corner-medium)",
                fontSize: "0.85rem",
              }}
            >
              <span>
                {version.product_niche || version.seller_type || "Untitled plan"} · {formatDate(version.created_at)}
              </span>
              <span style={{ display: "flex", gap: "0.5rem" }}>
                <md-text-button type="button" onClick={() => onActivate(version.id)}>
                  Make active
                </md-text-button>
                <md-text-button type="button" onClick={() => onDelete(version.id)}>
                  Delete
                </md-text-button>
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function OnboardingPage() {
  const navigate = useNavigate();
  const [activeProfile, setActiveProfile] = useState<BusinessProfile | null>(null);
  const [versions, setVersions] = useState<BusinessProfile[]>([]);
  const [categoryTree, setCategoryTree] = useState<CategoryTreeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  // null when creating a new plan/version; otherwise the version being edited.
  const [wizardTarget, setWizardTarget] = useState<BusinessProfile | null | undefined>(undefined);

  // Refreshes activeProfile/versions only -- never touches wizardTarget.
  // Callers that need to change which screen is showing do that
  // explicitly themselves; keeping the two concerns separate is what
  // makes this state easy to reason about instead of a shared "was this
  // the first load" heuristic.
  async function refreshData(): Promise<BusinessProfile | null> {
    const [active, all] = await Promise.all([api.getBusinessProfile(), api.listBusinessProfiles()]);
    setActiveProfile(active);
    setVersions(all);
    return active;
  }

  useEffect(() => {
    (async () => {
      try {
        const [active] = await Promise.all([
          refreshData(),
          api.getFilters().then((filters) => setCategoryTree(filters.category_tree)),
        ]);
        // Nothing to view yet -- go straight to the wizard instead of an
        // empty view screen with nothing in it.
        if (!active) setWizardTarget(null);
      } catch (e) {
        setLoadError(String(e));
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleWizardSubmit(fields: Record<string, string>, primaryCategoryId: number | null) {
    await api.synthesizeOnboarding(fields, primaryCategoryId, wizardTarget?.id ?? undefined);
    setWizardTarget(undefined);
    await refreshData();
  }

  async function handleActivate(id: number) {
    await api.activateBusinessProfile(id);
    await refreshData();
  }

  async function handleDelete(id: number) {
    await api.deleteBusinessProfile(id);
    const active = await refreshData();
    if (!active) setWizardTarget(null); // deleted the only plan -> back to the wizard
  }

  const wrapperStyle = {
    maxWidth: "32rem",
    margin: "0 auto",
    padding: "1.5rem 1rem",
  };

  if (loading) return <div style={wrapperStyle}>Loading...</div>;
  if (loadError) return <div style={{ ...wrapperStyle, color: "var(--md-sys-color-error)" }}>{loadError}</div>;

  if (wizardTarget !== undefined) {
    return (
      <div style={wrapperStyle}>
        {!activeProfile && (
          <div style={{ marginBottom: "1rem" }}>
            <h1 style={{ fontSize: "1.3rem", marginBottom: "0.25rem" }}>Tell us about your business</h1>
            <p style={{ fontSize: "0.85rem", color: "var(--md-sys-color-on-surface-variant)", margin: 0 }}>
              A few quick questions -- skip anything that doesn't apply. We'll use this to suggest a starting point,
              which you can always change or clear later.
            </p>
          </div>
        )}
        <WizardForm
          initialProfile={wizardTarget}
          categoryTree={categoryTree}
          onSubmit={handleWizardSubmit}
          onCancel={activeProfile ? () => setWizardTarget(undefined) : null}
        />
      </div>
    );
  }

  return (
    <div style={wrapperStyle}>
      {activeProfile && (
        <PlanView
          activeProfile={activeProfile}
          versions={versions}
          categoryTree={categoryTree}
          onEdit={() => setWizardTarget(activeProfile)}
          onNew={() => setWizardTarget(null)}
          onActivate={handleActivate}
          onDelete={handleDelete}
        />
      )}
      <div style={{ marginTop: "1.5rem" }}>
        <md-text-button type="button" onClick={() => navigate("/")}>
          Go to products
        </md-text-button>
      </div>
    </div>
  );
}
