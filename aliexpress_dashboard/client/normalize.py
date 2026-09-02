"""Defensive parsing at the API boundary.

aliexpress.ds.text.search and aliexpress.ds.product.get return genuinely
different shapes for the same product -- different field names, different
casing conventions (camelCase vs snake_case), and different nesting (flat
vs. nested DTOs) -- so there are two normalizer entry points below rather
than one. Nothing here should ever raise on bad input; unparseable values
are logged and become `None` (or `[]` for the image list) so one bad field
never aborts a run.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

from .models import NormalizedCategory, NormalizedProduct
from .raw import extract_list, get_field

logger = logging.getLogger(__name__)


def _str_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _normalize_url(value: Optional[str]) -> Optional[str]:
    """itemUrl comes back protocol-relative ("//www.aliexpress.com/...") --
    valid inside a browser's own page context, but not a URL you can open,
    export, or click from outside one (a CSV cell, a fresh tab). Confirmed
    live; give it a scheme so it works standalone."""
    if value is None:
        return None
    if value.startswith("//"):
        return f"https:{value}"
    return value


def parse_category_path(value: Any, *, field: str, product_id: Any) -> Optional[int]:
    """cateId comes back as a comma-separated category path
    ("66,200001147,201674401,200001313": root to leaf), not a single id --
    confirmed live, contradicting the docs' plain "Number" type. Takes the
    last (most specific) segment, matching how the old affiliate API's more
    specific "second level" category was the more useful one for filtering.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    last_segment = text.split(",")[-1].strip()
    return parse_int(last_segment, field=field, product_id=product_id)


def parse_percent(value: Any, *, field: str, product_id: Any) -> Optional[float]:
    """Parses a percentage field such as evaluate_rate ("91.3%") or discount ("40%")."""
    if value is None:
        return None
    if isinstance(value, bool):
        logger.warning("product %s: unexpected bool for %s: %r", product_id, field, value)
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().rstrip("%").strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            logger.warning("product %s: unparseable %s value %r", product_id, field, value)
            return None
    logger.warning("product %s: unexpected type for %s: %r", product_id, field, value)
    return None


def parse_price(value: Any, *, field: str, product_id: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        logger.warning("product %s: unexpected bool for %s: %r", product_id, field, value)
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            logger.warning("product %s: unparseable %s value %r", product_id, field, value)
            return None
    logger.warning("product %s: unexpected type for %s: %r", product_id, field, value)
    return None


def parse_int(value: Any, *, field: str, product_id: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        logger.warning("product %s: unexpected bool for %s: %r", product_id, field, value)
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(float(stripped))
        except ValueError:
            logger.warning("product %s: unparseable %s value %r", product_id, field, value)
            return None
    logger.warning("product %s: unexpected type for %s: %r", product_id, field, value)
    return None


def parse_bucketed_count(value: Any, *, field: str, product_id: Any) -> Tuple[Optional[int], Optional[str]]:
    """Sales/order counts on the ds.* API can be a bucketed display string
    like "1000+" rather than an exact number. Returns (best-effort numeric
    floor, original display text) so a bucketed count still sorts/filters
    sensibly without silently discarding the wording that made it bucketed."""
    if value is None:
        return None, None
    display = str(value)
    if isinstance(value, bool):
        logger.warning("product %s: unexpected bool for %s: %r", product_id, field, value)
        return None, display
    if isinstance(value, (int, float)):
        return int(value), display
    cleaned = display.strip().rstrip("+").replace(",", "").strip()
    if not cleaned:
        return None, display
    try:
        return int(float(cleaned)), display
    except ValueError:
        logger.warning("product %s: unparseable %s value %r", product_id, field, value)
        return None, display


def parse_str_list(value: Any, *, field: str, product_id: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [value] if value else []
    logger.warning("product %s: unparseable %s value %r, defaulting to []", product_id, field, value)
    return []


def normalize_search_product(raw: Any, *, target_currency: str) -> NormalizedProduct:
    """Normalizes one item from aliexpress.ds.text.search's `data.products` array."""
    product_id_raw = get_field(raw, "itemId")
    if product_id_raw is None:
        raise ValueError("search result product is missing itemId, cannot normalize")
    product_id = int(product_id_raw)

    sales_volume, sales_volume_display = parse_bucketed_count(
        get_field(raw, "orders"), field="orders", product_id=product_id
    )

    return NormalizedProduct(
        product_id=product_id,
        product_title=_str_or_none(get_field(raw, "title")),
        product_url=_normalize_url(_str_or_none(get_field(raw, "itemUrl"))),
        product_main_image_url=_str_or_none(get_field(raw, "itemMainPic")),
        product_video_url=_str_or_none(get_field(raw, "productVideoUrl")),
        category_id=parse_category_path(get_field(raw, "cateId"), field="cateId", product_id=product_id),
        sale_price=parse_price(get_field(raw, "salePrice"), field="salePrice", product_id=product_id),
        sale_price_currency=_str_or_none(get_field(raw, "salePriceCurrency")),
        original_price=parse_price(get_field(raw, "originalPrice"), field="originalPrice", product_id=product_id),
        original_price_currency=_str_or_none(get_field(raw, "originalPriceCurrency")),
        target_sale_price=parse_price(
            get_field(raw, "targetSalePrice"), field="targetSalePrice", product_id=product_id
        ),
        # The search response doesn't carry a distinct targetSalePriceCurrency
        # field -- target_sale_price is in whatever `currency` the request asked for.
        target_sale_price_currency=target_currency,
        discount=parse_percent(get_field(raw, "discount"), field="discount", product_id=product_id),
        evaluate_rate=parse_percent(get_field(raw, "evaluateRate"), field="evaluateRate", product_id=product_id),
        sales_volume=sales_volume,
        sales_volume_display=sales_volume_display,
    )


def normalize_detail_product(raw: Any, *, target_currency: str) -> NormalizedProduct:
    """Normalizes aliexpress.ds.product.get's `result` object.

    Pricing here lives per-SKU (a product can have many: colour, size,
    etc.), not as a single flat field like the search response -- this
    takes the first SKU as representative, the same simplification the
    original affiliate-based build made (one price per product, no variant
    handling). A multi-variant product's real price range won't be fully
    captured by that single value.
    """
    base = get_field(raw, "ae_item_base_info_dto") or {}
    product_id_raw = get_field(base, "product_id")
    if product_id_raw is None:
        raise ValueError("product detail payload is missing product_id, cannot normalize")
    product_id = int(product_id_raw)

    skus = extract_list(get_field(raw, "ae_item_sku_info_dtos"))
    first_sku = skus[0] if skus else {}

    multimedia = get_field(raw, "ae_multimedia_info_dto") or {}
    image_urls_raw = get_field(multimedia, "image_urls")  # semicolon-separated string, not a list
    images = [url for url in str(image_urls_raw).split(";") if url] if image_urls_raw else []

    videos = extract_list(get_field(multimedia, "ae_video_dtos"))
    video_url = _str_or_none(get_field(videos[0], "media_url")) if videos else None

    sales_volume, sales_volume_display = parse_bucketed_count(
        get_field(base, "sales_count"), field="sales_count", product_id=product_id
    )

    # sku_price is the higher "list" price, offer_sale_price the actual
    # current buy price -- confirmed live, both already in whatever
    # currency was requested (unlike the search response's sale_price,
    # which stays in the seller's native currency regardless of request).
    sku_currency = _str_or_none(get_field(first_sku, "currency_code")) or target_currency

    return NormalizedProduct(
        product_id=product_id,
        product_title=_str_or_none(get_field(base, "subject")),
        product_main_image_url=images[0] if images else None,
        product_small_image_urls=images,
        product_video_url=video_url,
        category_id=parse_int(get_field(base, "category_id"), field="category_id", product_id=product_id),
        sale_price=parse_price(get_field(first_sku, "sku_price"), field="sku_price", product_id=product_id),
        sale_price_currency=sku_currency,
        target_sale_price=parse_price(
            get_field(first_sku, "offer_sale_price"), field="offer_sale_price", product_id=product_id
        ),
        target_sale_price_currency=sku_currency,
        review_count=parse_int(get_field(base, "evaluation_count"), field="evaluation_count", product_id=product_id),
        avg_rating=parse_price(
            get_field(base, "avg_evaluation_rating"), field="avg_evaluation_rating", product_id=product_id
        ),
        sales_volume=sales_volume,
        sales_volume_display=sales_volume_display,
    )


def normalize_category(raw: Any) -> NormalizedCategory:
    category_id = int(get_field(raw, "category_id") or get_field(raw, "categoryId"))
    name = get_field(raw, "category_name")
    if name is None:
        name = get_field(raw, "categoryName")
    parent = get_field(raw, "parent_category_id")
    if parent is None:
        parent = get_field(raw, "parentCategoryId")
    return NormalizedCategory(
        category_id=category_id,
        category_name=str(name or ""),
        parent_category_id=parse_int(parent, field="parent_category_id", product_id=category_id),
    )
