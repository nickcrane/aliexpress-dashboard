from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

_VALID_SORTS = {
    None,
    "min_price,asc",
    "min_price,desc",
    "orders,asc",
    "orders,desc",
    "comments,asc",
    "comments,desc",
}


@dataclass
class NormalizedProduct:
    """A product, normalized into typed fields at the API boundary.

    Field set mirrors what's actually confirmed present across the two
    aliexpress.ds.* calls this client makes -- they return different shapes
    for the same product, so several fields are only ever populated from
    one of the two:

    - evaluate_rate (positive-feedback %) and product_url: search results only.
    - review_count and avg_rating (1-5 stars): detail lookups only. Getting
      these for a product means one extra API call, not something that
      comes for free while browsing search results.

    category_name is deliberately absent here -- neither endpoint returns a
    category name, only category_id. Use get_categories() to build an
    id -> name lookup if you need one; every reference to that lookup is
    unverified against a live response (see AliClient.get_categories).

    sale_price/sale_price_currency is the seller's/SKU's native price;
    target_sale_price/target_sale_price_currency is normalized to whatever
    currency was requested and is what every comparison, filter, and score
    should use.
    """

    product_id: int
    product_title: Optional[str] = None
    product_url: Optional[str] = None
    product_main_image_url: Optional[str] = None
    product_small_image_urls: List[str] = field(default_factory=list)
    product_video_url: Optional[str] = None
    category_id: Optional[int] = None
    sale_price: Optional[float] = None
    sale_price_currency: Optional[str] = None
    original_price: Optional[float] = None
    original_price_currency: Optional[str] = None
    target_sale_price: Optional[float] = None
    target_sale_price_currency: Optional[str] = None
    discount: Optional[float] = None  # percent, e.g. 40.0 for "40%"
    evaluate_rate: Optional[float] = None  # percent positive feedback; search results only
    review_count: Optional[int] = None  # detail lookups only
    avg_rating: Optional[float] = None  # 1-5 scale; detail lookups only
    sales_volume: Optional[int] = None  # best-effort parsed; see sales_volume_display
    sales_volume_display: Optional[str] = None  # the raw text -- ds.* sales counts can be
    # bucketed ("1000+") rather than exact, so the original wording is kept
    # alongside the parsed number rather than discarded.


@dataclass
class NormalizedCategory:
    category_id: int
    category_name: str
    parent_category_id: Optional[int] = None  # None means top-level


@dataclass
class SearchParams:
    """Params for aliexpress.ds.text.search. Unlike the affiliate API this
    replaces, `local` (language), `country_code` (ship-to destination), and
    `currency` are all required by the endpoint itself -- there's no
    unrestricted "search everything" mode.

    Price filtering is confirmed NOT to work server-side: tested live with
    `searchExtend` set two different plausible ways (a {searchKey: "price",
    min, max} object, and a bare {min, max} object in both major and minor
    currency units) and neither changed `totalCount` or the price spread of
    returned products at all -- results were identical to an unfiltered
    search either way. min_price/max_price are still accepted and still
    sent (harmless, and might start working, or a different structure might
    be found later), but don't rely on them to narrow what the collector
    fetches from AliExpress. This doesn't affect the dashboard's own price
    filter, which runs as a SQL WHERE clause over already-collected local
    data, not a live API call.
    """

    name: str
    keywords: Optional[str] = None
    category_id: Optional[int] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    price_currency: Optional[str] = None  # required if min_price/max_price is set
    sort: Optional[str] = None
    ship_to_country: Optional[str] = None  # overrides Settings.ship_to_country for this search
    page_no: int = 1
    page_size: int = 20
    selection_name: Optional[str] = None

    def __post_init__(self) -> None:
        if self.sort not in _VALID_SORTS:
            raise ValueError(f"Unknown sort {self.sort!r}; must be one of {sorted(s for s in _VALID_SORTS if s)}")
        if (self.min_price is not None or self.max_price is not None) and not self.price_currency:
            raise ValueError("price_currency is required when min_price/max_price is set")


@dataclass
class SearchResult:
    products: List[NormalizedProduct]
    current_page_no: int
    current_record_count: int
    total_record_count: int


@dataclass
class TokenSet:
    access_token: str
    refresh_token: Optional[str]
    expires_in: Optional[int]  # seconds
    refresh_expires_in: Optional[int]  # seconds
    obtained_at: str  # ISO 8601, when this token set was saved locally
