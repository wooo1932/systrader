import pytest
from src.engine.screener import Screener


@pytest.fixture
def screener():
    return Screener(
        max_holdings=3,
        min_market_cap=50_000_000_000,
        max_market_cap=1_000_000_000_000,
        min_change_pct=5.0,
        max_change_pct=28.0,
    )


def test_passes_valid_stock(screener):
    result = screener.check(
        market_cap=100_000_000_000, change_pct=10.0,
        current_price=50000, upper_limit_price=65000, current_holdings=0,
    )
    assert result.passed is True


def test_fails_too_many_holdings(screener):
    result = screener.check(
        market_cap=100_000_000_000, change_pct=10.0,
        current_price=50000, upper_limit_price=65000, current_holdings=3,
    )
    assert result.passed is False
    assert result.reason == "max_holdings"


def test_fails_market_cap_too_low(screener):
    result = screener.check(
        market_cap=10_000_000_000, change_pct=10.0,
        current_price=50000, upper_limit_price=65000, current_holdings=0,
    )
    assert result.passed is False
    assert result.reason == "min_market_cap"


def test_fails_market_cap_too_high(screener):
    result = screener.check(
        market_cap=2_000_000_000_000, change_pct=10.0,
        current_price=50000, upper_limit_price=65000, current_holdings=0,
    )
    assert result.passed is False
    assert result.reason == "max_market_cap"


def test_fails_change_pct_too_low(screener):
    result = screener.check(
        market_cap=100_000_000_000, change_pct=2.0,
        current_price=50000, upper_limit_price=65000, current_holdings=0,
    )
    assert result.passed is False
    assert result.reason == "min_change_pct"


def test_fails_change_pct_too_high(screener):
    result = screener.check(
        market_cap=100_000_000_000, change_pct=29.0,
        current_price=50000, upper_limit_price=65000, current_holdings=0,
    )
    assert result.passed is False
    assert result.reason == "max_change_pct"


def test_fails_price_near_upper_limit(screener):
    result = screener.check(
        market_cap=100_000_000_000, change_pct=10.0,
        current_price=64000, upper_limit_price=65000, current_holdings=0,
    )
    assert result.passed is False
    assert result.reason == "near_upper_limit"
