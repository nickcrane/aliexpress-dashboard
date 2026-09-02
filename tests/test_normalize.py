import pytest

from aliexpress_dashboard.client.normalize import (
    normalize_category,
    normalize_detail_product,
    normalize_search_product,
    parse_bucketed_count,
    parse_category_path,
    parse_int,
    parse_percent,
    parse_price,
)


def test_parse_percent_strips_percent_sign():
    assert parse_percent("91.3%", field="evaluate_rate", product_id=1) == 91.3


def test_parse_percent_accepts_bare_number():
    assert parse_percent(40, field="discount", product_id=1) == 40.0


def test_parse_percent_missing_is_none():
    assert parse_percent(None, field="evaluate_rate", product_id=1) is None


def test_parse_percent_garbage_logs_and_returns_none(caplog):
    with caplog.at_level("WARNING"):
        result = parse_percent("not-a-number", field="evaluate_rate", product_id=1)
    assert result is None
    assert "unparseable" in caplog.text


def test_parse_price_handles_string_decimal():
    assert parse_price("6.99", field="salePrice", product_id=1) == 6.99


def test_parse_price_garbage_does_not_raise():
    assert parse_price("N/A", field="salePrice", product_id=1) is None


def test_parse_int_zero_is_preserved_not_none():
    assert parse_int(0, field="orders", product_id=1) == 0


def test_parse_int_from_numeric_string():
    assert parse_int("3821", field="orders", product_id=1) == 3821


def test_parse_bucketed_count_exact_number():
    value, display = parse_bucketed_count("42", field="orders", product_id=1)
    assert value == 42
    assert display == "42"


def test_parse_bucketed_count_plus_suffix():
    value, display = parse_bucketed_count("1000+", field="sales_count", product_id=1)
    assert value == 1000
    assert display == "1000+"


def test_parse_bucketed_count_with_commas():
    value, display = parse_bucketed_count("10,000+", field="sales_count", product_id=1)
    assert value == 10000
    assert display == "10,000+"


def test_parse_bucketed_count_missing():
    assert parse_bucketed_count(None, field="orders", product_id=1) == (None, None)


def test_parse_bucketed_count_garbage_does_not_raise():
    value, display = parse_bucketed_count("orders", field="orders", product_id=1)
    assert value is None
    assert display == "orders"


def test_normalize_search_product_basic():
    raw = {
        "itemId": 1005006109529182,
        "title": "Widget",
        "itemUrl": "https://www.aliexpress.com/item/1005006109529182.html",
        "itemMainPic": "https://ae01.alicdn.com/kf/S1.jpg",
        "cateId": 1503,
        "salePrice": "6.99",
        "salePriceCurrency": "GBP",
        "targetSalePrice": "6.99",
        "discount": "42%",
        "evaluateRate": "96.7%",
        "orders": 3821,
    }
    product = normalize_search_product(raw, target_currency="GBP")

    assert product.product_id == 1005006109529182
    assert product.product_title == "Widget"
    assert product.category_id == 1503
    assert product.sale_price == 6.99
    assert product.target_sale_price == 6.99
    assert product.target_sale_price_currency == "GBP"
    assert product.evaluate_rate == 96.7
    assert product.sales_volume == 3821
    assert product.review_count is None  # search results never carry this
    assert product.avg_rating is None


def test_normalize_search_product_missing_evaluate_rate():
    raw = {"itemId": 1, "title": "No rating", "salePrice": "9.99"}
    product = normalize_search_product(raw, target_currency="GBP")
    assert product.evaluate_rate is None


def test_normalize_search_product_requires_item_id():
    with pytest.raises(ValueError):
        normalize_search_product({"title": "No id"}, target_currency="GBP")


def test_normalize_detail_product_full():
    raw = {
        "ae_item_base_info_dto": {
            "product_id": "1005006109529182",
            "subject": "Widget Detail",
            "category_id": "1503",
            "evaluation_count": "1042",
            "avg_evaluation_rating": "4.7",
            "sales_count": "3821",
        },
        "ae_item_sku_info_dtos": [
            {"sku_price": "6.99", "offer_sale_price": "6.99", "currency_code": "GBP"}
        ],
        "ae_multimedia_info_dto": {
            "image_urls": "https://ae01.alicdn.com/kf/S1a.jpg;https://ae01.alicdn.com/kf/S1b.jpg",
            "ae_video_dtos": [{"media_url": "https://media.aliexpress.com/video/1.mp4"}],
        },
    }
    product = normalize_detail_product(raw, target_currency="GBP")

    assert product.product_id == 1005006109529182
    assert product.product_title == "Widget Detail"
    assert product.category_id == 1503
    assert product.review_count == 1042
    assert product.avg_rating == 4.7
    assert product.sales_volume == 3821
    assert product.target_sale_price == 6.99
    assert product.target_sale_price_currency == "GBP"
    assert product.product_small_image_urls == [
        "https://ae01.alicdn.com/kf/S1a.jpg",
        "https://ae01.alicdn.com/kf/S1b.jpg",
    ]
    assert product.product_video_url == "https://media.aliexpress.com/video/1.mp4"


def test_normalize_detail_product_missing_evaluation_and_multimedia():
    raw = {
        "ae_item_base_info_dto": {
            "product_id": "1",
            "subject": "Bare Product",
            "sales_count": "0",
        },
        "ae_item_sku_info_dtos": [{"offer_sale_price": "2.49", "currency_code": "GBP"}],
    }
    product = normalize_detail_product(raw, target_currency="GBP")

    assert product.review_count is None
    assert product.avg_rating is None
    assert product.product_small_image_urls == []
    assert product.product_video_url is None
    assert product.sales_volume == 0  # a real zero, not "missing"


def test_normalize_detail_product_bucketed_sales_count():
    raw = {
        "ae_item_base_info_dto": {"product_id": "1", "subject": "Popular", "sales_count": "1000+"},
        "ae_item_sku_info_dtos": [{"offer_sale_price": "9.49", "currency_code": "GBP"}],
    }
    product = normalize_detail_product(raw, target_currency="GBP")
    assert product.sales_volume == 1000
    assert product.sales_volume_display == "1000+"


def test_normalize_detail_product_requires_product_id():
    with pytest.raises(ValueError):
        normalize_detail_product({"ae_item_base_info_dto": {"subject": "No id"}}, target_currency="GBP")


def test_normalize_category_distinguishes_parent_and_child():
    parent = normalize_category({"category_id": 15, "category_name": "Home & Garden"})
    child = normalize_category({"category_id": 1503, "category_name": "Lighting", "parent_category_id": 15})
    assert parent.parent_category_id is None
    assert child.parent_category_id == 15


def test_parse_category_path_takes_last_segment():
    # Confirmed live: cateId is a comma-separated root-to-leaf path, not a
    # single id ("66,200001147,201674401,200001313").
    assert parse_category_path("66,200001147,201674401,200001313", field="cateId", product_id=1) == 200001313


def test_parse_category_path_single_id_still_works():
    assert parse_category_path("1503", field="cateId", product_id=1) == 1503


def test_parse_category_path_missing_is_none():
    assert parse_category_path(None, field="cateId", product_id=1) is None


def test_normalize_search_product_fixes_protocol_relative_url():
    # Confirmed live: itemUrl comes back as "//www.aliexpress.com/..." --
    # valid inside a page, not clickable/openable standalone (a CSV cell, a
    # fresh tab) without a scheme.
    raw = {"itemId": 1, "title": "X", "itemUrl": "//www.aliexpress.com/item/1.html"}
    product = normalize_search_product(raw, target_currency="GBP")
    assert product.product_url == "https://www.aliexpress.com/item/1.html"


def test_normalize_search_product_leaves_absolute_url_alone():
    raw = {"itemId": 1, "title": "X", "itemUrl": "https://www.aliexpress.com/item/1.html"}
    product = normalize_search_product(raw, target_currency="GBP")
    assert product.product_url == "https://www.aliexpress.com/item/1.html"


def test_normalize_detail_product_sku_price_vs_offer_sale_price():
    # Confirmed live: sku_price is the higher "list" price, offer_sale_price
    # the actual current buy price -- both already in the requested
    # currency at the detail endpoint (unlike the search response, where
    # only target_sale_price is normalized and sale_price stays native).
    raw = {
        "ae_item_base_info_dto": {"product_id": "1", "subject": "X", "sales_count": "0"},
        "ae_item_sku_info_dtos": {
            "ae_item_sku_info_d_t_o": [
                {"sku_price": "18.54", "offer_sale_price": "5.19", "currency_code": "GBP"}
            ]
        },
    }
    product = normalize_detail_product(raw, target_currency="GBP")
    assert product.sale_price == 18.54
    assert product.target_sale_price == 5.19
    assert product.sale_price_currency == "GBP"
    assert product.target_sale_price_currency == "GBP"
