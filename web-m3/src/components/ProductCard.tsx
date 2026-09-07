import "@material/web/labs/card/filled-card.js";
import "@material/web/checkbox/checkbox.js";

import type { SyntheticEvent } from "react";

import type { Product } from "../types";

interface Props {
  product: Product;
  selected?: boolean;
  onToggle?: (productId: number, checked: boolean) => void;
  showCheckbox?: boolean;
}

export function ProductCard({ product, selected = false, onToggle, showCheckbox = true }: Props) {
  return (
    <md-filled-card style={{ display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {product.product_main_image_url ? (
        <img
          src={product.product_main_image_url}
          alt=""
          style={{ width: "100%", aspectRatio: "1", objectFit: "cover" }}
        />
      ) : (
        <div
          style={{
            width: "100%",
            aspectRatio: "1",
            background: "var(--md-sys-color-surface-container-high)",
          }}
        />
      )}
      <div style={{ padding: "0.75rem 1rem 1rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem" }}>
          {showCheckbox && (
            <md-checkbox
              checked={selected}
              onChange={(e: SyntheticEvent) =>
                onToggle?.(product.product_id, (e.target as HTMLInputElement).checked)
              }
            />
          )}
          <h3 style={{ margin: 0, fontSize: "0.95rem", lineHeight: 1.3 }}>{product.product_title}</h3>
        </div>
        {product.category_path && (
          <div style={{ fontSize: "0.75rem", color: "var(--md-sys-color-on-surface-variant)" }}>
            {product.category_path}
          </div>
        )}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <strong>
            {product.target_sale_price?.toFixed(2) ?? "?"} {product.target_sale_price_currency ?? ""}
          </strong>
          {product.discount ? (
            <span
              style={{
                fontSize: "0.75rem",
                padding: "0.1rem 0.5rem",
                borderRadius: "999px",
                background: "var(--md-sys-color-tertiary-container)",
                color: "var(--md-sys-color-on-tertiary-container)",
              }}
            >
              -{Math.round(product.discount)}%
            </span>
          ) : null}
        </div>
        <div style={{ fontSize: "0.8rem", color: "var(--md-sys-color-on-surface-variant)" }}>
          {product.evaluate_rate !== null ? `Rating: ${product.evaluate_rate.toFixed(1)}%` : "Rating: –"}
          {" · "}
          Volume: {product.sales_volume_display ?? product.sales_volume ?? 0}
        </div>
        {product.score !== undefined && (
          <div style={{ fontSize: "0.85rem" }}>
            Score: <strong>{product.score.toFixed(1)}</strong>
          </div>
        )}
        <a
          href={product.product_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: "0.85rem", color: "var(--md-sys-color-primary)" }}
        >
          View listing →
        </a>
      </div>
    </md-filled-card>
  );
}
