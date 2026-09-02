import json

from aliexpress_dashboard.client.ali_client import AliClient
from aliexpress_dashboard.client.tokens import load_token, save_token, seed_token_from_env
from aliexpress_dashboard.client.models import TokenSet
from aliexpress_dashboard.config import Settings

_VALID_SEED = json.dumps(
    {
        "access_token": "seeded-access-token",
        "refresh_token": "seeded-refresh-token",
        "expires_in": 86400,
        "refresh_expires_in": 172800,
        "obtained_at": "2026-01-01T00:00:00+00:00",
    }
)


def test_seed_writes_file_when_missing(tmp_path):
    path = tmp_path / "token.json"
    seed_token_from_env(path, _VALID_SEED)

    token = load_token(path)
    assert token is not None
    assert token.access_token == "seeded-access-token"


def test_seed_does_nothing_without_a_seed(tmp_path):
    path = tmp_path / "token.json"
    seed_token_from_env(path, None)
    assert not path.exists()


def test_seed_never_overwrites_an_existing_file(tmp_path):
    path = tmp_path / "token.json"
    existing = TokenSet(
        access_token="already-refreshed-token",
        refresh_token="already-refreshed-refresh-token",
        expires_in=86400,
        refresh_expires_in=172800,
        obtained_at="2026-06-01T00:00:00+00:00",
    )
    save_token(path, existing)

    seed_token_from_env(path, _VALID_SEED)

    token = load_token(path)
    assert token.access_token == "already-refreshed-token"  # untouched by the (older) seed


def test_seed_with_malformed_json_is_skipped_not_raised(tmp_path, caplog):
    path = tmp_path / "token.json"
    with caplog.at_level("WARNING"):
        seed_token_from_env(path, "{not valid json")
    assert not path.exists()
    assert "not valid token JSON" in caplog.text


def test_ali_client_picks_up_seeded_token_on_construction(tmp_path):
    settings = Settings(mode="fixture", token_path=tmp_path / "token.json", token_seed=_VALID_SEED)
    client = AliClient(settings)
    assert client._token.access_token == "seeded-access-token"


def test_ali_client_does_not_reseed_over_an_existing_token(tmp_path):
    token_path = tmp_path / "token.json"
    save_token(
        token_path,
        TokenSet(
            access_token="real-token",
            refresh_token="real-refresh",
            expires_in=86400,
            refresh_expires_in=172800,
            obtained_at="2026-06-01T00:00:00+00:00",
        ),
    )
    settings = Settings(mode="fixture", token_path=token_path, token_seed=_VALID_SEED)
    client = AliClient(settings)
    assert client._token.access_token == "real-token"
