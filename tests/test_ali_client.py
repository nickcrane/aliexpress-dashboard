import pytest

from aliexpress_dashboard.client import AliClient, FixtureNotFoundError, SearchParams
from aliexpress_dashboard.config import Settings


@pytest.fixture
def client():
    return AliClient(Settings(mode="fixture"))


def test_search_products_returns_normalized_results(client):
    params = SearchParams(name="home-gadgets-under-15-gbp")
    result = client.search_products(params)

    assert result.current_record_count == 3
    assert len(result.products) == 3

    by_id = {p.product_id: p for p in result.products}
    lamp = by_id[1005006109529182]
    assert lamp.evaluate_rate == 96.7
    assert lamp.sales_volume == 3821

    stopper = by_id[1005005123456789]
    assert stopper.evaluate_rate is None  # missing in the fixture, must not crash
    assert stopper.sales_volume == 0  # zero volume, must not collapse to None


def test_search_products_empty_result_returns_empty_list_not_exception(client):
    params = SearchParams(name="empty-search")
    result = client.search_products(params)

    assert result.products == []
    assert result.current_record_count == 0


def test_search_wrong_endpoint_price_requires_currency():
    with pytest.raises(ValueError):
        SearchParams(name="x", min_price=5.0)


def test_missing_fixture_raises_clear_error(client):
    params = SearchParams(name="does-not-exist")
    with pytest.raises(FixtureNotFoundError):
        client.search_products(params)


def test_get_product_detail_returns_normalized_product(client):
    product = client.get_product_detail(1005006109529182)
    assert product is not None
    assert product.product_id == 1005006109529182
    assert product.review_count == 1042
    assert product.avg_rating == 4.7


def test_get_product_detail_missing_fixture_raises(client):
    with pytest.raises(FixtureNotFoundError):
        client.get_product_detail(9999999999999999)


def test_get_categories_splits_parent_and_child(client):
    categories = client.get_categories()
    parents = [c for c in categories if c.parent_category_id is None]
    children = [c for c in categories if c.parent_category_id is not None]
    assert {c.category_name for c in parents} == {"Home & Garden", "Consumer Electronics"}
    assert any(c.category_name == "Lighting" and c.parent_category_id == 15 for c in children)


def test_search_params_requires_currency_with_price_band():
    with pytest.raises(ValueError):
        SearchParams(name="x", min_price=5.0)


def test_search_params_rejects_unknown_sort():
    with pytest.raises(ValueError):
        SearchParams(name="x", sort="bogus")


def test_search_params_accepts_valid_sort():
    params = SearchParams(name="x", sort="orders,desc")
    assert params.sort == "orders,desc"


def test_exchange_code_for_token_saves_and_returns_token(client, tmp_path, monkeypatch):
    from aliexpress_dashboard.config import Settings as S

    token_path = tmp_path / "token.json"
    fixture_client = AliClient(S(mode="fixture", token_path=token_path))
    token = fixture_client.exchange_code_for_token("fixture-code")

    assert token.access_token == "50000000-fixture-access-token"
    assert token.refresh_token == "50001001-fixture-refresh-token"
    assert token_path.exists()


def test_refresh_access_token_requires_existing_token(tmp_path):
    from aliexpress_dashboard.config import Settings as S

    fixture_client = AliClient(S(mode="fixture", token_path=tmp_path / "token.json"))
    with pytest.raises(Exception):
        fixture_client.refresh_access_token()


def test_refresh_access_token_updates_saved_token(tmp_path):
    from aliexpress_dashboard.config import Settings as S

    token_path = tmp_path / "token.json"
    fixture_client = AliClient(S(mode="fixture", token_path=token_path))
    fixture_client.exchange_code_for_token("fixture-code")

    refreshed = fixture_client.refresh_access_token()
    assert refreshed.access_token == "50000000-fixture-refreshed-access-token"


# -- envelope unwrapping / success-code checks -------------------------------
# Every case here is a shape confirmed against a real live account, not
# guessed -- this API family is genuinely inconsistent about how it wraps
# and signals success across its own endpoints.


def test_unwrap_envelope_no_wrapping():
    from aliexpress_dashboard.client.ali_client import _unwrap_envelope

    envelope = {"result": {"x": 1}, "rsp_code": "200"}
    assert _unwrap_envelope(envelope) == envelope


def test_unwrap_envelope_single_response_wrapper():
    from aliexpress_dashboard.client.ali_client import _unwrap_envelope

    envelope = {"aliexpress_ds_text_search_response": {"code": "00", "data": {}}}
    assert _unwrap_envelope(envelope) == {"code": "00", "data": {}}


def test_unwrap_envelope_response_plus_resp_result_wrapper():
    from aliexpress_dashboard.client.ali_client import _unwrap_envelope

    # resp_result has siblings (request_id, _trace_id_) -- not itself a
    # single-key dict, which is what broke the first version of this fix.
    envelope = {
        "aliexpress_ds_category_get_response": {
            "resp_result": {"result": {"categories": []}, "resp_code": 200},
            "request_id": "abc",
            "_trace_id_": "def",
        }
    }
    assert _unwrap_envelope(envelope) == {"result": {"categories": []}, "resp_code": 200}


def test_unwrap_envelope_leaves_non_matching_shape_alone():
    from aliexpress_dashboard.client.ali_client import _unwrap_envelope

    envelope = {"some_other_key": {"x": 1}}
    assert _unwrap_envelope(envelope) == envelope


def test_is_success_code_variants():
    from aliexpress_dashboard.client.ali_client import _is_success_code

    assert _is_success_code(None)
    assert _is_success_code("0")
    assert _is_success_code("00")
    assert _is_success_code(0)
    assert not _is_success_code("EXCEPTION_TEXT_SEARCH_FOR_DS")
    assert not _is_success_code("1")


def test_extract_list_bare_list():
    from aliexpress_dashboard.client.raw import extract_list

    assert extract_list([1, 2]) == [1, 2]


def test_extract_list_single_key_wrapper():
    from aliexpress_dashboard.client.raw import extract_list

    assert extract_list({"selection_search_product": [1, 2]}) == [1, 2]
    assert extract_list({"ae_item_sku_info_d_t_o": [{"a": 1}]}) == [{"a": 1}]


def test_extract_list_missing_or_empty():
    from aliexpress_dashboard.client.raw import extract_list

    assert extract_list(None) == []
    assert extract_list({}) == []
    assert extract_list("") == []
