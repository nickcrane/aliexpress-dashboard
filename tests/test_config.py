import pytest

from aliexpress_dashboard.config import Settings


def test_fixture_mode_needs_no_credentials():
    settings = Settings(mode="fixture", app_key=None, app_secret=None)
    assert settings.mode == "fixture"


def test_live_mode_requires_credentials():
    with pytest.raises(ValueError):
        Settings(mode="live", app_key=None, app_secret=None)


def test_live_mode_with_credentials_is_valid():
    settings = Settings(mode="live", app_key="k", app_secret="s")
    assert settings.app_key == "k"


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        Settings(mode="bogus")
