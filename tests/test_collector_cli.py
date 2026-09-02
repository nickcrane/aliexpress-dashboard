import pytest

from aliexpress_dashboard.collector.cli import main
from aliexpress_dashboard.db.connection import get_connection


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AE_MODE", "fixture")
    monkeypatch.setenv("AE_DB_PATH", str(tmp_path / "cli-test.db"))
    monkeypatch.delenv("AE_APP_KEY", raising=False)
    monkeypatch.delenv("AE_APP_SECRET", raising=False)
    return tmp_path


def test_add_search_then_list(capsys):
    assert main(["add-search", "--name", "lamp-search", "--keywords", "lamp"]) == 0

    assert main(["list-searches"]) == 0
    out = capsys.readouterr().out
    assert "lamp-search" in out
    assert "active" in out


def test_add_search_requires_currency_with_price_band(capsys):
    exit_code = main(["add-search", "--name", "s", "--min-price", "5"])
    assert exit_code == 2
    assert "currency" in capsys.readouterr().err


def test_list_searches_when_empty(capsys):
    assert main(["list-searches"]) == 0
    assert "No saved searches" in capsys.readouterr().out


def test_run_with_no_active_searches(capsys):
    assert main(["run"]) == 0
    assert "No active searches" in capsys.readouterr().err


def test_run_unknown_named_search(capsys):
    assert main(["run", "--search", "does-not-exist"]) == 2


def test_run_executes_saved_search_end_to_end(capsys, tmp_path):
    main(["add-search", "--name", "home-gadgets-under-15-gbp"])
    exit_code = main(["run"])
    assert exit_code == 0
    assert "3 records written" in capsys.readouterr().out

    conn = get_connection(tmp_path / "cli-test.db")
    assert len(conn.execute("SELECT * FROM products").fetchall()) == 3


def test_run_reports_nonzero_exit_when_a_search_errors(capsys):
    main(["add-search", "--name", "totally-missing-fixture"])
    exit_code = main(["run"])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "1 errors" in out
    assert "ERROR" in out


def test_authorize_requires_app_key(capsys):
    exit_code = main(["authorize"])
    assert exit_code == 2
    assert "AE_APP_KEY" in capsys.readouterr().err


def test_authorize_prints_url_when_no_code(capsys, monkeypatch):
    monkeypatch.setenv("AE_APP_KEY", "test-app-key")

    exit_code = main(["authorize"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "oauth/authorize" in out
    assert "test-app-key" in out


def test_authorize_with_code_exchanges_and_saves_token(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("AE_APP_KEY", "test-app-key")
    monkeypatch.setenv("AE_TOKEN_PATH", str(tmp_path / "token.json"))

    exit_code = main(["authorize", "--code", "fixture-code"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Authorized" in out
    assert (tmp_path / "token.json").exists()


def test_refresh_token_after_authorize(capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("AE_APP_KEY", "test-app-key")
    monkeypatch.setenv("AE_TOKEN_PATH", str(tmp_path / "token.json"))

    main(["authorize", "--code", "fixture-code"])
    capsys.readouterr()  # drain

    exit_code = main(["refresh-token"])
    assert exit_code == 0
    assert "Refreshed" in capsys.readouterr().out
