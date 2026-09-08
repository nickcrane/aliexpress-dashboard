import "@material/web/textfield/outlined-text-field.js";
import "@material/web/button/filled-button.js";
import "@material/web/button/outlined-button.js";

import { useEffect, useState } from "react";

import { api } from "../api";
import { FilterPanel } from "../components/FilterPanel";
import { ProductCard } from "../components/ProductCard";
import { computeCompositeScore } from "../scoring";
import type { FilterOptions, Product, ProductFilters, ScoreWeights } from "../types";
import { useMediaQuery } from "../useMediaQuery";

const DEFAULT_WEIGHTS: ScoreWeights = { volume: 25, rating: 25, review_count: 25, price_fit: 25 };

export function ProductsPage() {
  const [filters, setFilters] = useState<ProductFilters>({});
  const [weights, setWeights] = useState<ScoreWeights>(DEFAULT_WEIGHTS);
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    category_tree: [],
    currencies: [],
    ship_to_countries: [],
  });
  const [products, setProducts] = useState<Product[]>([]);
  const [priceCeiling, setPriceCeiling] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [shortlistName, setShortlistName] = useState("");
  const [panelOpen, setPanelOpen] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isDesktop = useMediaQuery("(min-width: 900px)");

  useEffect(() => {
    let cancelled = false;
    api
      .getFilters()
      .then((options) => !cancelled && setFilterOptions(options))
      // Non-fatal: the filter dropdowns just stay empty rather than
      // blocking the page with an error over otherwise-working content.
      .catch((e) => !cancelled && console.error("Failed to load filter options:", e));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    api
      .loadCurrentProducts(filters)
      .then((p) => !cancelled && setProducts(p))
      .catch((e) => !cancelled && setError(String(e)));
    if (filters.price_currency) {
      api.maxTargetPrice(filters.price_currency).then((p) => !cancelled && setPriceCeiling(p));
    } else {
      setPriceCeiling(null);
    }
    return () => {
      cancelled = true;
    };
  }, [filters]);

  const scores = computeCompositeScore(products, weights);
  const scoredProducts = products.map((p, i) => ({ ...p, score: scores[i] ?? undefined }));

  function toggleSelected(productId: number, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(productId);
      else next.delete(productId);
      return next;
    });
  }

  async function handleSave() {
    if (!shortlistName.trim()) return;
    setStatus(null);
    try {
      await api.saveShortlist(shortlistName.trim(), Array.from(selected));
      setStatus(`Added ${selected.size} product(s) to shortlist "${shortlistName.trim()}".`);
      setSelected(new Set());
      setShortlistName("");
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div style={{ display: "flex" }}>
      <FilterPanel
        filterOptions={filterOptions}
        filters={filters}
        weights={weights}
        priceCeiling={priceCeiling}
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        onApply={(f, w) => {
          setFilters(f);
          setWeights(w);
        }}
      />

      <main style={{ flex: 1, padding: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <h1 style={{ margin: 0, fontSize: "1.3rem" }}>
            {products.length} product{products.length !== 1 ? "s" : ""}
          </h1>
          {!isDesktop && (
            <md-outlined-button type="button" onClick={() => setPanelOpen(true)}>
              Filters
            </md-outlined-button>
          )}
        </div>

        {error && <div style={{ color: "var(--md-sys-color-error)", marginBottom: "1rem" }}>{error}</div>}
        {status && <div style={{ color: "var(--md-sys-color-primary)", marginBottom: "1rem" }}>{status}</div>}

        {products.length === 0 ? (
          <p>No products match these filters yet. Loosen the filters, or run the collector.</p>
        ) : (
          <>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
                gap: "1rem",
                marginBottom: "1.5rem",
              }}
            >
              {scoredProducts.map((p) => (
                <ProductCard
                  key={p.product_id}
                  product={p}
                  selected={selected.has(p.product_id)}
                  onToggle={toggleSelected}
                />
              ))}
            </div>

            <div
              style={{
                display: "flex",
                gap: "0.75rem",
                alignItems: "center",
                flexWrap: "wrap",
                background: "var(--md-sys-color-surface-container-low)",
                padding: "1rem",
                borderRadius: "var(--md-sys-shape-corner-medium)",
              }}
            >
              <md-outlined-text-field
                label="Save selected to shortlist"
                value={shortlistName}
                oninput={(e: Event) => setShortlistName((e.target as HTMLInputElement).value)}
                style={{ flex: 1, minWidth: "200px" }}
              />
              <md-filled-button type="button" disabled={selected.size === 0} onClick={handleSave}>
                Save {selected.size} selected
              </md-filled-button>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
