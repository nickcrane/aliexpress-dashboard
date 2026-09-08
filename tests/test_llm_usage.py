import pytest

from aliexpress_dashboard.dashboard import llm_usage
from aliexpress_dashboard.db.connection import get_connection
from aliexpress_dashboard.db.migrate import run_migrations


@pytest.fixture
def conn(tmp_path):
    connection = get_connection(tmp_path / "test.db")
    run_migrations(connection)
    return connection


def test_current_month_cost_is_zero_with_no_usage(conn):
    assert llm_usage.current_month_cost_usd(conn) == 0.0


def test_record_usage_computes_cost_from_real_haiku_pricing(conn):
    # 1,000,000 input + 1,000,000 output tokens at $1.00/$5.00 per 1M.
    cost = llm_usage.record_usage(conn, input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == pytest.approx(6.00)
    assert llm_usage.current_month_cost_usd(conn) == pytest.approx(6.00)


def test_record_usage_accumulates_across_calls(conn):
    llm_usage.record_usage(conn, input_tokens=100_000, output_tokens=50_000)
    llm_usage.record_usage(conn, input_tokens=200_000, output_tokens=100_000)
    # (100k+200k)*$1/1M + (50k+100k)*$5/1M = 0.30 + 0.75
    assert llm_usage.current_month_cost_usd(conn) == pytest.approx(1.05)


def test_is_over_cap(conn):
    llm_usage.record_usage(conn, input_tokens=10_000_000, output_tokens=0)  # $10.00
    assert llm_usage.is_over_cap(conn, cap_usd=20.0) is False
    assert llm_usage.is_over_cap(conn, cap_usd=10.0) is True
    assert llm_usage.is_over_cap(conn, cap_usd=5.0) is True


def test_usage_is_scoped_per_month(conn, monkeypatch):
    llm_usage.record_usage(conn, input_tokens=1_000_000, output_tokens=0)  # $1.00 this month
    monkeypatch.setattr(llm_usage, "current_month", lambda: "2099-01")
    assert llm_usage.current_month_cost_usd(conn) == 0.0  # a different month, no usage yet
    llm_usage.record_usage(conn, input_tokens=2_000_000, output_tokens=0)  # $2.00 in 2099-01
    assert llm_usage.current_month_cost_usd(conn) == pytest.approx(2.00)
