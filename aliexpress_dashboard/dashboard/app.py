"""Streamlit dashboard. Run via the project-root launcher, not this file
directly -- `streamlit run` executes its target as a top-level script, which
would break the package-relative imports below:

    streamlit run run_dashboard.py
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..config import get_settings
from .api_client import ApiClient
from .export import to_csv_bytes, to_xlsx_bytes
from .queries import ProductFilters
from .scoring import ScoreWeights, compute_composite_score

PRODUCT_TABLE_COLUMN_CONFIG = {
    "product_main_image_url": st.column_config.ImageColumn("Image"),
    "product_title": st.column_config.TextColumn("Title", width="large"),
    "target_sale_price": st.column_config.NumberColumn("Price", format="%.2f"),
    "target_sale_price_currency": st.column_config.TextColumn("Currency"),
    "evaluate_rate": st.column_config.NumberColumn("Rating", format="%.1f%%"),
    "avg_rating": st.column_config.NumberColumn("Stars", format="%.1f", help="1-5 scale; needs a detail lookup, blank otherwise"),
    "review_count": st.column_config.NumberColumn("Reviews", help="Needs a detail lookup, blank otherwise"),
    "sales_volume": st.column_config.NumberColumn("Volume", help="Best-effort parsed; hover a row's raw value in the export for bucketed counts like '1000+'"),
    "discount": st.column_config.NumberColumn("Discount", format="%.0f%%"),
    "score": st.column_config.NumberColumn("Score", format="%.1f", help="Composite score from the sidebar weights"),
    "price_history": st.column_config.LineChartColumn(
        "Price history", help="Needs 2+ observations; blank until then"
    ),
    "listing": st.column_config.LinkColumn("Listing"),
}


def _sidebar_filters(client: ApiClient) -> ProductFilters:
    filter_options = client.get_filters()
    category_ids = filter_options.categories
    currencies = filter_options.currencies
    ship_to_options = filter_options.ship_to_countries

    st.header("Filters")

    currency = None
    if currencies:
        currency = st.selectbox("Currency", currencies, index=0)
        if len(currencies) > 1:
            st.caption(
                "Multiple currencies are present in this database "
                "(AE_TARGET_CURRENCY changed at some point). Price "
                "filtering only ever compares within the one selected."
            )

    category_choice = None
    if category_ids:
        category_choice = st.selectbox(
            "Category",
            options=[None] + category_ids,
            format_func=lambda cid: "All categories" if cid is None else f"Category {cid}",
            help="ds.* doesn't return a category name, only an id -- see README.",
        )

    min_price = max_price = price_currency = None
    if currency:
        price_ceiling = max(client.max_target_price(currency) or 500.0, 1.0)
        min_price, max_price = st.slider(f"Price band ({currency})", 0.0, float(price_ceiling), (0.0, float(price_ceiling)))
        price_currency = currency

    min_rating = st.slider("Minimum rating (evaluate_rate %)", 0, 100, 0) or None
    min_volume = st.number_input("Minimum sales volume", min_value=0, value=0, step=10) or None

    ship_to_country = st.selectbox(
        "Ship to country", options=[None] + ship_to_options, format_func=lambda c: "Any" if c is None else c
    )

    return ProductFilters(
        category_id=category_choice,
        min_price=min_price,
        max_price=max_price,
        price_currency=price_currency,
        min_rating=min_rating,
        min_volume=min_volume,
        ship_to_country=ship_to_country,
    )


def _sidebar_score_weights() -> ScoreWeights:
    st.header("Score weights")
    st.caption(
        "Composite score = weighted blend of these four, each ranked relative "
        "to the products currently shown. Price fit rewards a *lower* price "
        "within your filtered band. Review count is usually 0/neutral for "
        "everything -- it only gets populated by a per-product detail "
        "lookup, which the collector doesn't run automatically for every "
        "search result (see README)."
    )
    return ScoreWeights(
        volume=st.slider("Sales volume weight", 0, 100, 25),
        rating=st.slider("Rating weight", 0, 100, 25),
        review_count=st.slider("Review count weight", 0, 100, 25),
        price_fit=st.slider("Price-fit weight (lower price wins)", 0, 100, 25),
    )


def _render_products_tab(client: ApiClient, df: pd.DataFrame) -> None:
    if df.empty:
        st.info(
            "No products match these filters yet. "
            "Run the collector (`aliexpress_dashboard.collector.cli run`), or loosen the filters."
        )
        return

    display_df = df.reset_index(drop=True).copy()
    display_df["listing"] = display_df["product_url"]

    price_history = client.load_price_history(display_df["product_id"].tolist())
    display_df["price_history"] = display_df["product_id"].map(lambda pid: price_history.get(pid, []))

    weights = st.session_state["score_weights"]
    display_df["score"] = compute_composite_score(display_df, weights)

    columns = [
        "product_main_image_url",
        "product_title",
        "target_sale_price",
        "target_sale_price_currency",
        "evaluate_rate",
        "avg_rating",
        "review_count",
        "sales_volume",
        "discount",
        "score",
        "price_history",
        "listing",
    ]

    event = st.dataframe(
        display_df[columns],
        column_config=PRODUCT_TABLE_COLUMN_CONFIG,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="multi-row",
        key="products_table",
    )

    selected_positions = event.selection.rows if event else []
    selected_product_ids = display_df.iloc[selected_positions]["product_id"].tolist() if selected_positions else []

    st.divider()
    col1, col2 = st.columns([3, 1])
    with col1:
        shortlist_name = st.text_input(
            "Shortlist name",
            placeholder="e.g. Q1 candidates",
            help="Tick rows above, name a shortlist (new or existing), then save.",
        )
    with col2:
        st.write("")  # vertical alignment with the text input's label
        save_clicked = st.button(f"Save {len(selected_product_ids)} selected", disabled=not selected_product_ids)

    if save_clicked:
        if not shortlist_name.strip():
            st.warning("Enter a shortlist name first.")
        else:
            client.save_shortlist(shortlist_name.strip(), selected_product_ids)
            st.success(f"Added {len(selected_product_ids)} product(s) to shortlist '{shortlist_name.strip()}'.")

    col1, col2 = st.columns(2)
    with col1:
        st.download_button("Download CSV", data=to_csv_bytes(df), file_name="aliexpress_products.csv", mime="text/csv")
    with col2:
        st.download_button(
            "Download XLSX",
            data=to_xlsx_bytes(df),
            file_name="aliexpress_products.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def _render_momentum_tab(client: ApiClient, df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No products match the current filters, so there's nothing to show momentum for.")
        return

    window_days = st.number_input("Rolling window (days)", min_value=1, value=14, step=1)

    momentum = client.get_momentum(df["product_id"].tolist(), window_days=window_days)

    if momentum.empty or momentum["volume_change"].isna().all():
        st.info(
            "No product here has two observations yet, so there's no change to "
            "rank. Run the collector again on a later day to start building history."
        )
        return

    merged = momentum.merge(
        df[["product_id", "product_title", "product_main_image_url", "product_url"]],
        on="product_id",
        how="left",
    )
    merged["listing"] = merged["product_url"]
    merged = merged.sort_values("volume_change", ascending=False, na_position="last")

    st.dataframe(
        merged[
            [
                "product_main_image_url",
                "product_title",
                "latest_volume",
                "previous_volume",
                "volume_change",
                "volume_change_pct",
                "window_start_volume",
                "window_volume_change",
                "window_volume_change_pct",
                "listing",
            ]
        ],
        column_config={
            "product_main_image_url": st.column_config.ImageColumn("Image"),
            "product_title": st.column_config.TextColumn("Title", width="large"),
            "latest_volume": st.column_config.NumberColumn("Latest volume"),
            "previous_volume": st.column_config.NumberColumn("Previous volume"),
            "volume_change": st.column_config.NumberColumn("Change (last run)"),
            "volume_change_pct": st.column_config.NumberColumn("Change % (last run)", format="%.1f%%"),
            "window_start_volume": st.column_config.NumberColumn(f"Volume {window_days}d ago"),
            "window_volume_change": st.column_config.NumberColumn(f"Change ({window_days}d)"),
            "window_volume_change_pct": st.column_config.NumberColumn(f"Change % ({window_days}d)", format="%.1f%%"),
            "listing": st.column_config.LinkColumn("Listing"),
        },
        hide_index=True,
        width="stretch",
    )


def _render_shortlists_tab(client: ApiClient) -> None:
    shortlists = client.list_shortlists()
    if not shortlists:
        st.info("No shortlists yet. Select some products in the Products tab and save a shortlist.")
        return

    options = {f"{s.name} ({s.item_count})": s for s in shortlists}
    chosen_label = st.selectbox("Shortlist", options=list(options.keys()))
    shortlist = options[chosen_label]

    products = client.load_shortlist_products(shortlist.id)

    if products.empty:
        st.info("This shortlist is empty.")
    else:
        display_df = products.copy()
        display_df["listing"] = display_df["product_url"]

        st.dataframe(
            display_df[
                [
                    "product_main_image_url",
                    "product_title",
                    "target_sale_price",
                    "target_sale_price_currency",
                    "evaluate_rate",
                    "avg_rating",
                    "review_count",
                    "sales_volume",
                    "discount",
                    "listing",
                ]
            ],
            column_config=PRODUCT_TABLE_COLUMN_CONFIG,
            hide_index=True,
            width="stretch",
        )

        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                "Download CSV",
                data=to_csv_bytes(products),
                file_name=f"{shortlist.name}.csv",
                mime="text/csv",
                key="shortlist_csv",
            )
        with col2:
            st.download_button(
                "Download XLSX",
                data=to_xlsx_bytes(products),
                file_name=f"{shortlist.name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="shortlist_xlsx",
            )

    st.divider()
    remove_col, delete_col = st.columns(2)
    with remove_col:
        if not products.empty:
            to_remove = st.selectbox(
                "Remove a product from this shortlist",
                options=products["product_id"].tolist(),
                format_func=lambda pid: products.set_index("product_id").loc[pid, "product_title"],
                key="remove_product_select",
            )
            if st.button("Remove"):
                client.remove_product_from_shortlist(shortlist.id, to_remove)
                st.rerun()
    with delete_col:
        if st.button(f"Delete shortlist '{shortlist.name}'", type="secondary"):
            client.delete_shortlist(shortlist.id)
            st.rerun()


def main() -> None:
    st.set_page_config(page_title="AliExpress Product Research", layout="wide")

    settings = get_settings()
    client = ApiClient(base_url=settings.api_base_url, api_key=settings.api_key)

    st.title("AliExpress Product Research")
    st.caption(f"Mode: {settings.mode} · API: {settings.api_base_url}")

    with st.sidebar:
        filters = _sidebar_filters(client)
        st.divider()
        st.session_state["score_weights"] = _sidebar_score_weights()

    df = client.load_current_products(filters)
    st.subheader(f"{len(df)} product{'s' if len(df) != 1 else ''}")

    tab_products, tab_momentum, tab_shortlists = st.tabs(["Products", "Momentum", "Shortlists"])
    with tab_products:
        _render_products_tab(client, df)
    with tab_momentum:
        _render_momentum_tab(client, df)
    with tab_shortlists:
        _render_shortlists_tab(client)


if __name__ == "__main__":
    main()
