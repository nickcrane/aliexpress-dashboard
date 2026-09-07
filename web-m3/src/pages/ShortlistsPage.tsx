import "@material/web/select/outlined-select.js";
import "@material/web/select/select-option.js";
import "@material/web/button/outlined-button.js";

import { useEffect, useState } from "react";

import { api } from "../api";
import { ProductCard } from "../components/ProductCard";
import type { Product, ShortlistSummary } from "../types";

export function ShortlistsPage() {
  const [shortlists, setShortlists] = useState<ShortlistSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState<string | null>(null);

  function refreshShortlists(preferId?: number) {
    api
      .listShortlists()
      .then((list) => {
        setShortlists(list);
        const next = preferId ?? (list.length > 0 ? list[0].id : null);
        setSelectedId(next);
      })
      .catch((e) => setError(String(e)));
  }

  useEffect(() => {
    refreshShortlists();
  }, []);

  useEffect(() => {
    if (selectedId === null) {
      setProducts([]);
      return;
    }
    api
      .loadShortlistProducts(selectedId)
      .then(setProducts)
      .catch((e) => setError(String(e)));
  }, [selectedId]);

  async function handleRemove(productId: number) {
    if (selectedId === null) return;
    await api.removeProductFromShortlist(selectedId, productId);
    setProducts((prev) => prev.filter((p) => p.product_id !== productId));
    refreshShortlists(selectedId);
  }

  async function handleDelete() {
    if (selectedId === null) return;
    await api.deleteShortlist(selectedId);
    refreshShortlists();
  }

  return (
    <main style={{ padding: "1rem" }}>
      <h1 style={{ fontSize: "1.3rem" }}>Shortlists</h1>
      {error && <div style={{ color: "var(--md-sys-color-error)" }}>{error}</div>}

      {shortlists.length === 0 ? (
        <p>No shortlists yet. Select some products on the Products page and save a shortlist.</p>
      ) : (
        <>
          <div style={{ display: "flex", gap: "1rem", alignItems: "center", flexWrap: "wrap", marginBottom: "1.5rem" }}>
            <md-outlined-select
              label="Shortlist"
              value={selectedId?.toString() ?? ""}
              onchange={(e: Event) => setSelectedId(Number((e.target as HTMLSelectElement).value))}
              style={{ minWidth: "260px" }}
            >
              {shortlists.map((s) => (
                <md-select-option key={s.id} value={s.id.toString()}>
                  <div slot="headline">
                    {s.name} ({s.item_count})
                  </div>
                </md-select-option>
              ))}
            </md-outlined-select>
            <md-outlined-button type="button" onClick={handleDelete}>
              Delete this shortlist
            </md-outlined-button>
          </div>

          {products.length === 0 ? (
            <p>This shortlist is empty.</p>
          ) : (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
                gap: "1rem",
              }}
            >
              {products.map((p) => (
                <div key={p.product_id}>
                  <ProductCard product={p} showCheckbox={false} />
                  <md-outlined-button
                    type="button"
                    onClick={() => handleRemove(p.product_id)}
                    style={{ marginTop: "0.5rem" }}
                  >
                    Remove
                  </md-outlined-button>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </main>
  );
}
