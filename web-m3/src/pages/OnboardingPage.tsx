import "@material/web/textfield/outlined-text-field.js";
import "@material/web/button/filled-button.js";
import "@material/web/button/outlined-button.js";
import "@material/web/button/text-button.js";

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
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

// The finished-plan view is styled after Notion's "Startup Pitch Deck"
// template (gradient hero band with a badge mark, a bold pull-quote
// statement, light "callout" stat cards, section dividers, pill tags for
// list-style fields) rather than the plain field-list this used to be --
// it's the one screen meant to be read/shown off rather than edited, so
// it's worth it looking like a pitch deck rather than a data dump. Built
// entirely from inline styles + the app's existing --md-sys-color-*
// tokens (theme.css) so it stays correct in dark mode without any new
// hardcoded colors.

function heroBlockStyle(top: number, left: number, size: number, rotate: number, opacity: number): CSSProperties {
  return {
    position: "absolute",
    top,
    left,
    width: size,
    height: size,
    borderRadius: "18%",
    background: "var(--md-sys-color-primary)",
    opacity,
    transform: `rotate(${rotate}deg)`,
  };
}

function HeroBand({ title, tagline }: { title: string; tagline?: string }) {
  return (
    <div
      style={{
        position: "relative",
        overflow: "hidden",
        borderRadius: "var(--md-sys-shape-corner-large)",
        background:
          "linear-gradient(135deg, var(--md-sys-color-primary-container), var(--md-sys-color-tertiary-container))",
        padding: "2.5rem 1.5rem",
      }}
    >
      <div style={heroBlockStyle(-24, -24, 90, 18, 0.3)} />
      <div style={heroBlockStyle(-36, 70, 60, -14, 0.22)} />
      <div style={{ ...heroBlockStyle(30, 0, 70, 28, 0.18), left: "auto", right: -20 }} />
      <div
        style={{
          position: "relative",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "0.85rem",
          textAlign: "center",
        }}
      >
        <div
          style={{
            width: 52,
            height: 52,
            borderRadius: "50%",
            background: "var(--md-sys-color-surface-container-lowest)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            boxShadow: "0 2px 10px rgba(0, 0, 0, 0.18)",
          }}
        >
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8z" fill="var(--md-sys-color-primary)" />
          </svg>
        </div>
        <h1
          style={{
            fontSize: "1.6rem",
            margin: 0,
            color: "var(--md-sys-color-on-primary-container)",
          }}
        >
          {title}
        </h1>
        {tagline && (
          <p
            style={{
              margin: 0,
              maxWidth: "30rem",
              color: "var(--md-sys-color-on-primary-container)",
              opacity: 0.9,
              lineHeight: 1.5,
            }}
          >
            {tagline}
          </p>
        )}
      </div>
    </div>
  );
}

function Divider() {
  return <hr style={{ border: "none", borderTop: "1px solid var(--md-sys-color-outline-variant)", margin: 0 }} />;
}

function SectionHeading({ children }: { children: ReactNode }) {
  return <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0 }}>{children}</h2>;
}

function StatCard({ icon, label, value }: { icon: string; label: string; value: string }) {
  return (
    <div
      style={{
        flex: "1 1 12rem",
        background: "var(--md-sys-color-secondary-container)",
        color: "var(--md-sys-color-on-secondary-container)",
        borderRadius: "var(--md-sys-shape-corner-medium)",
        padding: "1rem 1.1rem",
      }}
    >
      <div style={{ fontSize: "1.1rem", marginBottom: "0.4rem" }} aria-hidden="true">
        {icon}
      </div>
      <div style={{ fontSize: "0.78rem", opacity: 0.85 }}>{label}</div>
      <div style={{ fontSize: "0.95rem", fontWeight: 600 }}>{value}</div>
    </div>
  );
}

function Pill({ children }: { children: ReactNode }) {
  return (
    <span
      style={{
        display: "inline-block",
        padding: "0.3rem 0.7rem",
        borderRadius: "999px",
        background: "var(--md-sys-color-tertiary-container)",
        color: "var(--md-sys-color-on-tertiary-container)",
        fontSize: "0.8rem",
        fontWeight: 600,
      }}
    >
      {children}
    </span>
  );
}

function PillGroup({ label, values }: { label: string; values: string[] }) {
  if (values.length === 0) return null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
      <span style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--md-sys-color-on-surface-variant)" }}>
        {label}
      </span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        {values.map((v) => (
          <Pill key={v}>{v}</Pill>
        ))}
      </div>
    </div>
  );
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
  const sellerLabel = SELLER_TYPES.find(([v]) => v === activeProfile.seller_type)?.[1];
  const budgetLabel = BUDGET_STAGES.find(([v]) => v === activeProfile.budget_stage)?.[1];
  const salesLabels = activeProfile.sales_channels.map(
    (v) => SALES_CHANNELS.find(([value]) => value === v)?.[1] ?? v,
  );
  const marketingLabels = activeProfile.marketing_approach.map(
    (v) => MARKETING_APPROACHES.find(([value]) => value === v)?.[1] ?? v,
  );
  const hasOpportunity = Boolean(activeProfile.product_niche || activeProfile.target_market);
  const hasGoToMarket = salesLabels.length > 0 || marketingLabels.length > 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
      <HeroBand
        title={activeProfile.product_niche ? activeProfile.product_niche : "Your business plan"}
        tagline={activeProfile.summary || undefined}
      />

      {(sellerLabel || categoryName) && (
        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
          {sellerLabel && <StatCard icon="🧑‍💼" label="Seller type" value={sellerLabel} />}
          {categoryName && <StatCard icon="📦" label="Category" value={categoryName} />}
        </div>
      )}

      {hasOpportunity && (
        <>
          <Divider />
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <SectionHeading>The opportunity</SectionHeading>
            <p style={{ margin: 0, lineHeight: 1.6 }}>
              {activeProfile.product_niche && (
                <>
                  Selling <strong>{activeProfile.product_niche}</strong>
                </>
              )}
              {activeProfile.product_niche && activeProfile.target_market && " to "}
              {activeProfile.target_market && <strong>{activeProfile.target_market}</strong>}
              {(activeProfile.product_niche || activeProfile.target_market) && "."}
            </p>
          </div>
        </>
      )}

      {activeProfile.market_gap_analysis && (
        <>
          <Divider />
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <SectionHeading>Market gap analysis</SectionHeading>
            <div
              style={{
                background: "var(--md-sys-color-tertiary-container)",
                color: "var(--md-sys-color-on-tertiary-container)",
                borderRadius: "var(--md-sys-shape-corner-medium)",
                padding: "1rem 1.1rem",
                lineHeight: 1.6,
              }}
            >
              <div style={{ fontSize: "1.1rem", marginBottom: "0.4rem" }} aria-hidden="true">
                🔎
              </div>
              {activeProfile.market_gap_analysis}
            </div>
            <span style={{ fontSize: "0.75rem", color: "var(--md-sys-color-on-surface-variant)" }}>
              Based on {categoryName ?? "the selected category"}'s currently tracked listings -- price, demand, and
              competition signals, not guesswork.
            </span>
          </div>
        </>
      )}

      {hasGoToMarket && (
        <>
          <Divider />
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <SectionHeading>Go-to-market</SectionHeading>
            <PillGroup label="Sales channels" values={salesLabels} />
            <PillGroup label="Marketing approach" values={marketingLabels} />
          </div>
        </>
      )}

      {budgetLabel && (
        <>
          <Divider />
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            <SectionHeading>Stage</SectionHeading>
            <div>
              <Pill>{budgetLabel}</Pill>
            </div>
          </div>
        </>
      )}

      <Divider />

      <div style={{ display: "flex", gap: "0.75rem" }}>
        <md-filled-button type="button" onClick={onEdit}>
          Edit this plan
        </md-filled-button>
        <md-outlined-button type="button" onClick={onNew}>
          Create new version
        </md-outlined-button>
      </div>

      {otherVersions.length > 0 && (
        <>
          <Divider />
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <SectionHeading>Other versions</SectionHeading>
            {otherVersions.map((version) => (
              <div
                key={version.id}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "0.75rem",
                  background: "var(--md-sys-color-surface-container-lowest)",
                  border: "1px solid var(--md-sys-color-outline-variant)",
                  padding: "0.7rem 0.9rem",
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
        </>
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
    <div style={{ ...wrapperStyle, maxWidth: "42rem" }}>
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
