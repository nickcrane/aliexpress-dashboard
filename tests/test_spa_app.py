"""Tests for spa/app.py: the /api/* proxy (auth enforced, then forwarded
to a real API server with the key attached) and the static SPA fallback."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aliexpress_dashboard.client.ali_client import AliClient
from aliexpress_dashboard.client.models import NormalizedCategory
from aliexpress_dashboard.collector import store
from aliexpress_dashboard.collector.runner import run_collection
from aliexpress_dashboard.config import Settings, get_settings
from aliexpress_dashboard.db.connection import get_connection
from aliexpress_dashboard.db.migrate import run_migrations
from aliexpress_dashboard.spa import app as spa_app_module
from aliexpress_dashboard.spa.app import app
from aliexpress_dashboard.spa.security import require_firebase_login

API_KEY = "test-spa-key"


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = get_connection(db_path)
    run_migrations(conn)
    store.upsert_search(conn, name="home-gadgets-under-15-gbp")
    saved = store.get_search_by_name(conn, "home-gadgets-under-15-gbp")
    client = AliClient(Settings(mode="fixture"))
    run_collection(conn, client, mode="fixture", searches=[saved])
    store.upsert_categories(
        conn,
        [
            NormalizedCategory(category_id=1420, category_name="Tools"),
            # The fixture's real "home-gadgets-under-15-gbp" search collects
            # a product under this id (see test_onboarding_synthesize_
            # fetches_real_market_stats_for_the_chosen_category) --
            # primary_category_id has an FK to this table, so it needs a row.
            NormalizedCategory(category_id=1509, category_name="Kitchen Tools"),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def client(live_api_base_url, seeded_db, monkeypatch):
    monkeypatch.setenv("AE_MODE", "fixture")
    monkeypatch.setenv("AE_DB_PATH", str(seeded_db))
    monkeypatch.setenv("AE_API_KEY", API_KEY)
    settings = Settings(
        mode="fixture",
        db_path=seeded_db,
        api_key=API_KEY,
        api_base_url=live_api_base_url,
        firebase_project_id="test-project",
        dashboard_allowed_emails="allowed@example.com",
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_health_needs_no_auth(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_proxy_without_login_is_rejected(client):
    response = client.get("/api/filters")
    assert response.status_code == 401


def test_proxy_forwards_to_real_backend_once_logged_in(client):
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    response = client.get("/api/filters")
    assert response.status_code == 200
    assert "categories" in response.json()


def test_proxy_forwards_query_params_and_status(client):
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    # No currency param -> the real API 422s; confirms errors pass through too.
    response = client.get("/api/filters/max-price")
    assert response.status_code == 422


def test_proxy_forwards_content_type_for_json_post_bodies(client):
    # Regression: the backend can't parse a POST body as JSON without a
    # Content-Type header -- confirmed live this proxy was forwarding the
    # raw bytes without it, 422ing every JSON-bodied route (e.g. saving a
    # shortlist) proxied through here.
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    response = client.post("/api/shortlists", json={"name": "Q1 candidates", "product_ids": []})
    assert response.status_code == 200
    assert response.json()["name"] == "Q1 candidates"


def test_spa_fallback_reports_missing_build_when_dist_absent(client, tmp_path, monkeypatch):
    monkeypatch.setattr(spa_app_module, "DIST_DIR", tmp_path / "nonexistent-dist")
    response = client.get("/momentum")
    assert response.status_code == 503
    assert "npm run build" in response.text


def test_spa_fallback_serves_index_html_for_router_paths(client, tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>the app shell</html>")
    monkeypatch.setattr(spa_app_module, "DIST_DIR", dist)

    response = client.get("/momentum")
    assert response.status_code == 200
    assert "the app shell" in response.text


def test_spa_fallback_serves_real_files_directly(client, tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>the app shell</html>")
    (dist / "vite.svg").write_text("<svg>icon</svg>")
    monkeypatch.setattr(spa_app_module, "DIST_DIR", dist)

    response = client.get("/vite.svg")
    assert response.status_code == 200
    assert "icon" in response.text


# ----------------------------------------------- business profile proxy ---


def test_business_profile_proxy_requires_login(client):
    assert client.get("/api/business-profile").status_code == 401
    assert client.get("/api/business-profiles").status_code == 401
    assert client.post("/api/business-profiles", json={}).status_code == 401


def test_create_business_profile_proxy_uses_verified_email_not_client_supplied(client):
    # The core security property: a client claiming to be someone else in
    # the request body must not be able to write to that user's profile.
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    response = client.post(
        "/api/business-profiles",
        json={"user_email": "someone-else@example.com", "seller_type": "reseller"},
    )
    assert response.status_code == 200
    assert response.json()["user_email"] == "allowed@example.com"


def test_update_business_profile_proxy_uses_verified_email_not_client_supplied(client):
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    created = client.post("/api/business-profiles", json={"seller_type": "reseller"}).json()

    # A different verified caller must not be able to edit this profile,
    # even if they claim (correctly or not) to be its owner in the body.
    app.dependency_overrides[require_firebase_login] = lambda: "attacker@example.com"
    response = client.put(
        f"/api/business-profiles/{created['id']}",
        json={"user_email": "allowed@example.com", "seller_type": "hijacked"},
    )
    assert response.status_code == 404


def test_business_profile_proxy_create_and_get_round_trip(client):
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    create_response = client.post(
        "/api/business-profiles",
        json={"seller_type": "content_creator", "product_niche": "kitchen gadgets"},
    )
    assert create_response.status_code == 200

    get_response = client.get("/api/business-profile")
    assert get_response.status_code == 200
    assert get_response.json()["product_niche"] == "kitchen gadgets"


def test_business_profile_proxy_404_when_none_saved(client):
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    assert client.get("/api/business-profile").status_code == 404


def test_business_profile_proxy_list_and_activate(client):
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    first = client.post("/api/business-profiles", json={"seller_type": "reseller"}).json()
    client.post("/api/business-profiles", json={"seller_type": "influencer"})

    versions = client.get("/api/business-profiles").json()
    assert len(versions) == 2

    activate_response = client.post(f"/api/business-profiles/{first['id']}/activate")
    assert activate_response.status_code == 200
    assert client.get("/api/business-profile").json()["id"] == first["id"]


def test_business_profile_proxy_delete(client):
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    created = client.post("/api/business-profiles", json={"seller_type": "reseller"}).json()
    delete_response = client.delete(f"/api/business-profiles/{created['id']}")
    assert delete_response.status_code == 200
    assert client.get("/api/business-profile").status_code == 404


# --------------------------------------------------------- onboarding ---


def test_onboarding_synthesize_requires_login(client):
    assert client.post("/api/onboarding/synthesize", json={"answers": {}}).status_code == 401


def test_onboarding_synthesize_fails_closed_without_anthropic_key(client):
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    response = client.post("/api/onboarding/synthesize", json={"answers": {}})
    assert response.status_code == 503
    assert "AE_ANTHROPIC_API_KEY" in response.json()["detail"]


def _override_settings(client, **extra):
    from dataclasses import replace

    base = client.app.dependency_overrides[get_settings]()
    app.dependency_overrides[get_settings] = lambda: replace(base, **extra)


def test_onboarding_synthesize_respects_monthly_cap(client):
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    # Push this month's usage (on the real backend behind `client`, via
    # the generic proxy) to $2.00, then cap at $1.00.
    record = client.post("/api/llm-usage/record", json={"input_tokens": 2_000_000, "output_tokens": 0})
    assert record.status_code == 200

    _override_settings(client, anthropic_api_key="test-anthropic-key", llm_monthly_cap_usd=1.0)
    # synthesize_business_plan is deliberately NOT mocked here: if the cap
    # check didn't short-circuit, this would instead try a real network
    # call with a fake key and fail with a different error than the cap
    # message below.
    response = client.post("/api/onboarding/synthesize", json={"answers": {}})
    assert response.status_code == 503
    assert "spending cap" in response.json()["detail"]


def test_onboarding_synthesize_happy_path(client, monkeypatch):
    async def fake_synthesize(*, api_key, wizard_answers, market_stats=None):
        from aliexpress_dashboard.client.llm_client import SynthesizedPlan

        assert api_key == "test-anthropic-key"
        assert wizard_answers == {"niche": "kitchen gadgets"}
        return SynthesizedPlan(
            seller_type="content_creator",
            product_niche="kitchen gadgets",
            target_market="young home cooks",
            sales_channels=["tiktok_shop"],
            marketing_approach=["organic_content"],
            budget_stage="just_starting",
            summary="A content creator selling kitchen gadgets.",
            market_gap_analysis="The under-£5 band is saturated; £8+ has less competition.",
            tiktok_shop_angle="Small kitchen gadgets suit quick demo-style unboxing clips.",
            input_tokens=500,
            output_tokens=150,
        )

    monkeypatch.setattr(spa_app_module, "synthesize_business_plan", fake_synthesize)
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    _override_settings(client, anthropic_api_key="test-anthropic-key", llm_monthly_cap_usd=20.0)

    response = client.post(
        "/api/onboarding/synthesize",
        json={"answers": {"niche": "kitchen gadgets"}, "primary_category_id": 1420},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["seller_type"] == "content_creator"
    assert body["status"] == "complete"
    assert body["user_email"] == "allowed@example.com"
    # Picked directly by the client (Material Web chips), not inferred by
    # the LLM -- passed straight through.
    assert body["primary_category_id"] == 1420
    assert body["market_gap_analysis"] == "The under-£5 band is saturated; £8+ has less competition."
    assert body["tiktok_shop_angle"] == "Small kitchen gadgets suit quick demo-style unboxing clips."
    # Category 1420 has no collected products in this fixture -- no real
    # stats behind the numbers, so nothing gets frozen into the snapshot.
    assert body["category_stats_snapshot"] is None

    # Usage got recorded against the real backend: $1/1M*500 + $5/1M*150
    usage = client.get("/api/llm-usage/current-month")
    assert usage.json()["cost_usd"] == pytest.approx(0.00125)


def test_onboarding_synthesize_fetches_real_market_stats_for_the_chosen_category(client, monkeypatch):
    # End to end against the real backend (via live_api_base_url): category
    # 1509 has exactly one product (2.49 GBP) in this fixture -- confirms
    # the spa route actually calls the real /categories/{id}/market-stats
    # route and forwards its output, not a stub.
    captured = {}

    async def fake_synthesize(*, api_key, wizard_answers, market_stats=None):
        from aliexpress_dashboard.client.llm_client import SynthesizedPlan

        captured["market_stats"] = market_stats
        return SynthesizedPlan(seller_type=None, product_niche=None, target_market=None, summary="x")

    monkeypatch.setattr(spa_app_module, "synthesize_business_plan", fake_synthesize)
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    _override_settings(client, anthropic_api_key="test-anthropic-key", llm_monthly_cap_usd=20.0)

    response = client.post(
        "/api/onboarding/synthesize",
        json={"answers": {}, "primary_category_id": 1509},
    )
    assert response.status_code == 200
    assert captured["market_stats"]["product_count"] == 1
    assert captured["market_stats"]["price_min"] == 2.49

    # The same stats get frozen onto the saved profile, for the plan view
    # to show without a live re-query drifting from the LLM's prose.
    body = response.json()
    assert body["category_stats_snapshot"]["product_count"] == 1
    assert body["category_stats_snapshot"]["price_min"] == 2.49


def test_onboarding_synthesize_without_a_category_sends_no_market_stats(client, monkeypatch):
    captured = {}

    async def fake_synthesize(*, api_key, wizard_answers, market_stats=None):
        from aliexpress_dashboard.client.llm_client import SynthesizedPlan

        captured["market_stats"] = market_stats
        return SynthesizedPlan(seller_type=None, product_niche=None, target_market=None, summary="x")

    monkeypatch.setattr(spa_app_module, "synthesize_business_plan", fake_synthesize)
    app.dependency_overrides[require_firebase_login] = lambda: "allowed@example.com"
    _override_settings(client, anthropic_api_key="test-anthropic-key", llm_monthly_cap_usd=20.0)

    response = client.post("/api/onboarding/synthesize", json={"answers": {}})
    assert response.status_code == 200
    assert captured["market_stats"] is None
