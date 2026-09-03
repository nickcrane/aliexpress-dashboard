"""Thin HTTP client web/app.py uses instead of touching SQLite directly --
talks to the routes in aliexpress_dashboard/api/app.py. Method signatures
mirror the queries.py/momentum.py/shortlists.py functions those routes
wrap server-side.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx
import pandas as pd

from .queries import ProductFilters
from .shortlists import ShortlistSummary

_MOMENTUM_COLUMNS = [
    "product_id",
    "latest_volume",
    "latest_captured_at",
    "previous_volume",
    "volume_change",
    "volume_change_pct",
    "window_start_volume",
    "window_volume_change",
    "window_volume_change_pct",
]


@dataclass
class FilterOptions:
    categories: List[int]
    currencies: List[str]
    ship_to_countries: List[str]


class ApiClient:
    def __init__(self, *, base_url: str, api_key: Optional[str]) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"X-API-Key": api_key} if api_key else {},
        )

    def close(self) -> None:
        self._client.close()

    def load_current_products(self, filters: ProductFilters) -> pd.DataFrame:
        params = {k: v for k, v in filters.__dict__.items() if v is not None}
        response = self._client.get("/products", params=params)
        response.raise_for_status()
        return pd.DataFrame(response.json())

    def load_price_history(self, product_ids: List[int]) -> Dict[int, List[float]]:
        if not product_ids:
            return {}
        response = self._client.get(
            "/products/price-history", params={"product_ids": ",".join(map(str, product_ids))}
        )
        response.raise_for_status()
        return {int(k): v for k, v in response.json().items()}

    def get_filters(self) -> FilterOptions:
        response = self._client.get("/filters")
        response.raise_for_status()
        data = response.json()
        return FilterOptions(**data)

    def max_target_price(self, currency: str) -> Optional[float]:
        response = self._client.get("/filters/max-price", params={"currency": currency})
        response.raise_for_status()
        return response.json()["max_price"]

    def get_momentum(self, product_ids: List[int], *, window_days: int = 14) -> pd.DataFrame:
        if not product_ids:
            return pd.DataFrame(columns=_MOMENTUM_COLUMNS)
        response = self._client.get(
            "/momentum",
            params={"product_ids": ",".join(map(str, product_ids)), "window_days": window_days},
        )
        response.raise_for_status()
        return pd.DataFrame(response.json(), columns=_MOMENTUM_COLUMNS)

    def list_shortlists(self) -> List[ShortlistSummary]:
        response = self._client.get("/shortlists")
        response.raise_for_status()
        return [ShortlistSummary(**item) for item in response.json()]

    def load_shortlist_products(self, shortlist_id: int) -> pd.DataFrame:
        response = self._client.get(f"/shortlists/{shortlist_id}/products")
        response.raise_for_status()
        return pd.DataFrame(response.json())

    def save_shortlist(self, name: str, product_ids: List[int]) -> None:
        response = self._client.post("/shortlists", json={"name": name, "product_ids": product_ids})
        response.raise_for_status()

    def remove_product_from_shortlist(self, shortlist_id: int, product_id: int) -> None:
        response = self._client.delete(f"/shortlists/{shortlist_id}/products/{product_id}")
        response.raise_for_status()

    def delete_shortlist(self, shortlist_id: int) -> None:
        response = self._client.delete(f"/shortlists/{shortlist_id}")
        response.raise_for_status()
