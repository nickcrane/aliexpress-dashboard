import "@material/web/textfield/outlined-text-field.js";
import "@material/web/button/filled-button.js";

import { useEffect, useState } from "react";

import { api } from "../api";
import type { MomentumRow, Product, ProductFilters } from "../types";

function fmt(value: number | null, suffix = ""): string {
  return value === null ? "–" : `${value}${suffix}`;
}

export function MomentumPage() {
  const [windowDays, setWindowDays] = useState(14);
  const [inputDays, setInputDays] = useState("14");
  const [momentum, setMomentum] = useState<MomentumRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    api
      .loadCurrentProducts({} as ProductFilters)
      .then((products: Product[]) => {
        const productIds = products.map((p) => p.product_id);
        return api.getMomentum(productIds, windowDays).then((rows) => {
          if (cancelled) return;
          const byId = new Map(products.map((p) => [p.product_id, p]));
          setMomentum(
            rows.map((row) => {
              const p = byId.get(row.product_id);
              return {
                ...row,
                product_title: p?.product_title,
                product_main_image_url: p?.product_main_image_url,
                product_url: p?.product_url,
              };
            }),
          );
        });
      })
      .catch((e) => setError(String(e)));
    return () => {
      cancelled = true;
    };
  }, [windowDays]);

  return (
    <main style={{ padding: "1rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem", marginBottom: "1rem" }}>
        <h1 style={{ margin: 0, fontSize: "1.3rem" }}>Momentum</h1>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const n = Number(inputDays);
            if (n > 0) setWindowDays(n);
          }}
          style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}
        >
          <md-outlined-text-field
            label="Rolling window (days)"
            type="number"
            value={inputDays}
            oninput={(e: Event) => setInputDays((e.target as HTMLInputElement).value)}
            style={{ width: "10rem" }}
          />
          <md-filled-button type="submit">Update</md-filled-button>
        </form>
      </div>

      {error && <div style={{ color: "var(--md-sys-color-error)" }}>{error}</div>}

      {momentum.length === 0 ? (
        <p>
          No product here has two observations yet, so there's no change to rank. Run the collector again on a
          later day to start building history.
        </p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "right", borderBottom: "1px solid var(--md-sys-color-outline-variant)" }}>
                <th style={{ textAlign: "left", padding: "0.5rem" }}>Title</th>
                <th style={{ padding: "0.5rem" }}>Latest volume</th>
                <th style={{ padding: "0.5rem" }}>Previous volume</th>
                <th style={{ padding: "0.5rem" }}>Change (last run)</th>
                <th style={{ padding: "0.5rem" }}>Change % (last run)</th>
                <th style={{ padding: "0.5rem" }}>Volume {windowDays}d ago</th>
                <th style={{ padding: "0.5rem" }}>Change ({windowDays}d)</th>
                <th style={{ padding: "0.5rem" }}>Change % ({windowDays}d)</th>
              </tr>
            </thead>
            <tbody>
              {momentum.map((m) => (
                <tr key={m.product_id} style={{ borderBottom: "1px solid var(--md-sys-color-outline-variant)" }}>
                  <td style={{ padding: "0.5rem" }}>
                    {m.product_url ? (
                      <a href={m.product_url} target="_blank" rel="noopener noreferrer">
                        {m.product_title ?? m.product_id}
                      </a>
                    ) : (
                      m.product_title ?? m.product_id
                    )}
                  </td>
                  <td style={{ padding: "0.5rem", textAlign: "right" }}>{fmt(m.latest_volume)}</td>
                  <td style={{ padding: "0.5rem", textAlign: "right" }}>{fmt(m.previous_volume)}</td>
                  <td style={{ padding: "0.5rem", textAlign: "right" }}>{fmt(m.volume_change)}</td>
                  <td style={{ padding: "0.5rem", textAlign: "right" }}>
                    {m.volume_change_pct === null ? "–" : `${m.volume_change_pct.toFixed(1)}%`}
                  </td>
                  <td style={{ padding: "0.5rem", textAlign: "right" }}>{fmt(m.window_start_volume)}</td>
                  <td style={{ padding: "0.5rem", textAlign: "right" }}>{fmt(m.window_volume_change)}</td>
                  <td style={{ padding: "0.5rem", textAlign: "right" }}>
                    {m.window_volume_change_pct === null ? "–" : `${m.window_volume_change_pct.toFixed(1)}%`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
