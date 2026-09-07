import "@material/web/textfield/outlined-text-field.js";
import "@material/web/select/outlined-select.js";
import "@material/web/select/select-option.js";
import "@material/web/slider/slider.js";
import "@material/web/button/filled-button.js";
import "@material/web/iconbutton/icon-button.js";

import { type FormEvent, useState } from "react";

import type { FilterOptions, ProductFilters, ScoreWeights } from "../types";
import { useMediaQuery } from "../useMediaQuery";

interface Props {
  filterOptions: FilterOptions;
  filters: ProductFilters;
  weights: ScoreWeights;
  priceCeiling: number | null;
  open: boolean;
  onClose: () => void;
  onApply: (filters: ProductFilters, weights: ScoreWeights) => void;
}

export function FilterPanel({ filterOptions, filters, weights, priceCeiling, open, onClose, onApply }: Props) {
  const isDesktop = useMediaQuery("(min-width: 900px)");
  const [draftFilters, setDraftFilters] = useState<ProductFilters>(filters);
  const [draftWeights, setDraftWeights] = useState<ScoreWeights>(weights);

  const visible = isDesktop || open;

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onApply(draftFilters, draftWeights);
    if (!isDesktop) onClose();
  }

  function field<K extends keyof ProductFilters>(key: K, value: string) {
    setDraftFilters((prev) => ({
      ...prev,
      [key]: value === "" ? undefined : (Number.isNaN(Number(value)) ? value : Number(value)) as never,
    }));
  }

  if (!visible) return null;

  return (
    <>
      {!isDesktop && (
        <div
          onClick={onClose}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", zIndex: 10 }}
        />
      )}
      <form
        onSubmit={handleSubmit}
        style={{
          position: isDesktop ? "static" : "fixed",
          top: 0,
          bottom: 0,
          left: 0,
          zIndex: 11,
          width: isDesktop ? "auto" : "min(85vw, 320px)",
          background: "var(--md-sys-color-surface-container-low)",
          padding: "1rem",
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
          boxShadow: isDesktop ? "none" : "2px 0 8px rgba(0,0,0,0.2)",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Filters</h2>
          {!isDesktop && (
            <md-icon-button type="button" onClick={onClose} aria-label="Close">
              ✕
            </md-icon-button>
          )}
        </div>

        <md-outlined-select
          label="Currency"
          value={draftFilters.price_currency ?? ""}
          onchange={(e: Event) => field("price_currency", (e.target as HTMLSelectElement).value)}
        >
          <md-select-option value="">
            <div slot="headline">Any</div>
          </md-select-option>
          {filterOptions.currencies.map((c) => (
            <md-select-option key={c} value={c}>
              <div slot="headline">{c}</div>
            </md-select-option>
          ))}
        </md-outlined-select>

        <md-outlined-select
          label="Category"
          value={draftFilters.category_id?.toString() ?? ""}
          onchange={(e: Event) => field("category_id", (e.target as HTMLSelectElement).value)}
        >
          <md-select-option value="">
            <div slot="headline">All categories</div>
          </md-select-option>
          {filterOptions.categories.map((c) => (
            <md-select-option key={c.category_id} value={c.category_id.toString()}>
              <div slot="headline">{c.category_path ?? `Category ${c.category_id}`}</div>
            </md-select-option>
          ))}
        </md-outlined-select>

        <div style={{ display: "flex", gap: "0.5rem" }}>
          <md-outlined-text-field
            label="Min price"
            type="number"
            value={draftFilters.min_price?.toString() ?? ""}
            oninput={(e: Event) => field("min_price", (e.target as HTMLInputElement).value)}
          />
          <md-outlined-text-field
            label="Max price"
            type="number"
            value={draftFilters.max_price?.toString() ?? ""}
            oninput={(e: Event) => field("max_price", (e.target as HTMLInputElement).value)}
          />
        </div>
        {priceCeiling !== null && (
          <div style={{ fontSize: "0.75rem", color: "var(--md-sys-color-on-surface-variant)" }}>
            Highest price currently in this currency: {priceCeiling.toFixed(2)}
          </div>
        )}

        <md-outlined-text-field
          label="Minimum rating (%)"
          type="number"
          value={draftFilters.min_rating?.toString() ?? ""}
          oninput={(e: Event) => field("min_rating", (e.target as HTMLInputElement).value)}
        />
        <md-outlined-text-field
          label="Minimum sales volume"
          type="number"
          value={draftFilters.min_volume?.toString() ?? ""}
          oninput={(e: Event) => field("min_volume", (e.target as HTMLInputElement).value)}
        />

        <md-outlined-select
          label="Ship to country"
          value={draftFilters.ship_to_country ?? ""}
          onchange={(e: Event) => field("ship_to_country", (e.target as HTMLSelectElement).value)}
        >
          <md-select-option value="">
            <div slot="headline">Any</div>
          </md-select-option>
          {filterOptions.ship_to_countries.map((c) => (
            <md-select-option key={c} value={c}>
              <div slot="headline">{c}</div>
            </md-select-option>
          ))}
        </md-outlined-select>

        <hr style={{ width: "100%", border: "none", borderTop: "1px solid var(--md-sys-color-outline-variant)" }} />
        <h3 style={{ margin: 0, fontSize: "0.95rem" }}>Score weights</h3>
        {(
          [
            ["volume", "Sales volume"],
            ["rating", "Rating"],
            ["review_count", "Review count"],
            ["price_fit", "Price fit (lower price wins)"],
          ] as const
        ).map(([key, label]) => (
          <div key={key}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.85rem" }}>
              <span>{label}</span>
              <span>{draftWeights[key]}</span>
            </div>
            <md-slider
              min={0}
              max={100}
              value={draftWeights[key]}
              oninput={(e: Event) =>
                setDraftWeights((prev) => ({ ...prev, [key]: Number((e.target as HTMLInputElement).value) }))
              }
            />
          </div>
        ))}

        <md-filled-button type="submit">Apply filters</md-filled-button>
      </form>
    </>
  );
}
