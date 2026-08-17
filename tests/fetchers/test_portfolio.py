import json
from pathlib import Path

import pandas as pd
import pytest
from pytest_mock import MockerFixture

from app.fetchers.portfolio import (
    DEFAULT_PORTFOLIO_PATH,
    PortfolioConfigError,
    PortfolioQuote,
    Symbol,
    fetch_portfolio_prices,
    fetch_quote,
    load_portfolio,
)


def _write_config(tmp_path: Path, payload: object) -> Path:
    config_path = tmp_path / "portfolio.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    return config_path


def _mock_yfinance(mocker: MockerFixture, closes_by_ticker: dict[str, list[float]]) -> None:
    """Patch yf.Ticker so history() serves canned closes instead of hitting the network."""

    def fake_ticker(ticker: str) -> object:
        handle = mocker.Mock()
        handle.history.return_value = pd.DataFrame({"Close": closes_by_ticker.get(ticker, [])})
        return handle

    mocker.patch("app.fetchers.portfolio.yf.Ticker", side_effect=fake_ticker)


def test_default_portfolio_path_points_at_repo_config() -> None:
    assert DEFAULT_PORTFOLIO_PATH.parent.name == "config"
    assert DEFAULT_PORTFOLIO_PATH.name == "portfolio.json"
    assert (DEFAULT_PORTFOLIO_PATH.parent / "portfolio.example.json").is_file()


def test_load_portfolio_reads_symbols_in_order(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        {"symbols": [{"ticker": "TSLA", "label": "Tesla"}, {"ticker": "IWM", "label": "Russell"}]},
    )

    symbols = load_portfolio(config_path)

    assert symbols == [Symbol("TSLA", "Tesla"), Symbol("IWM", "Russell")]


def test_load_portfolio_defaults_label_to_ticker(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, {"symbols": [{"ticker": " TSLA "}]})

    assert load_portfolio(config_path) == [Symbol("TSLA", "TSLA")]


def test_load_portfolio_raises_when_file_missing(tmp_path: Path) -> None:
    with pytest.raises(PortfolioConfigError, match="cp config/portfolio.example.json"):
        load_portfolio(tmp_path / "does-not-exist.json")


def test_load_portfolio_raises_when_json_invalid(tmp_path: Path) -> None:
    config_path = tmp_path / "portfolio.json"
    config_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(PortfolioConfigError, match="not valid JSON"):
        load_portfolio(config_path)


@pytest.mark.parametrize("payload", [[], {}, {"symbols": "TSLA"}])
def test_load_portfolio_raises_when_symbols_list_missing(tmp_path: Path, payload: object) -> None:
    with pytest.raises(PortfolioConfigError, match="'symbols' list"):
        load_portfolio(_write_config(tmp_path, payload))


def test_load_portfolio_raises_when_entry_is_not_an_object(tmp_path: Path) -> None:
    with pytest.raises(PortfolioConfigError, match="non-object entry"):
        load_portfolio(_write_config(tmp_path, {"symbols": ["TSLA"]}))


@pytest.mark.parametrize("entry", [{"label": "No ticker"}, {"ticker": ""}, {"ticker": 123}])
def test_load_portfolio_raises_when_ticker_missing(tmp_path: Path, entry: object) -> None:
    with pytest.raises(PortfolioConfigError, match="missing 'ticker'"):
        load_portfolio(_write_config(tmp_path, {"symbols": [entry]}))


def test_fetch_quote_computes_close_and_change_pct(mocker: MockerFixture) -> None:
    _mock_yfinance(mocker, {"TSLA": [100.0, 110.0]})

    quote = fetch_quote(Symbol("TSLA", "Tesla"))

    assert quote.close == 110.0
    assert quote.change_pct == pytest.approx(10.0)
    assert quote.label == "Tesla"


def test_fetch_quote_requests_a_multi_day_window(mocker: MockerFixture) -> None:
    """A single-day window would return no previous close on Mondays and holidays."""
    ticker_factory = mocker.patch("app.fetchers.portfolio.yf.Ticker")
    ticker_factory.return_value.history.return_value = pd.DataFrame({"Close": [100.0, 110.0]})

    fetch_quote(Symbol("TSLA", "Tesla"))

    ticker_factory.return_value.history.assert_called_once_with(period="5d")


def test_fetch_quote_handles_missing_symbol(mocker: MockerFixture) -> None:
    """An unknown ticker yields empty history from yfinance rather than an exception."""
    _mock_yfinance(mocker, {})

    quote = fetch_quote(Symbol("NOSUCHTICKER", "Bogus"))

    assert quote == PortfolioQuote("NOSUCHTICKER", "Bogus", close=None, change_pct=None)


def test_fetch_quote_handles_yfinance_exception(mocker: MockerFixture) -> None:
    mocker.patch("app.fetchers.portfolio.yf.Ticker", side_effect=RuntimeError("network down"))

    quote = fetch_quote(Symbol("TSLA", "Tesla"))

    assert quote == PortfolioQuote("TSLA", "Tesla", close=None, change_pct=None)


def test_fetch_quote_without_previous_close_has_no_change_pct(mocker: MockerFixture) -> None:
    _mock_yfinance(mocker, {"KOID": [42.5]})

    quote = fetch_quote(Symbol("KOID", "Humanoid Robotics"))

    assert quote.close == 42.5
    assert quote.change_pct is None


def test_fetch_quote_with_zero_previous_close_has_no_change_pct(mocker: MockerFixture) -> None:
    _mock_yfinance(mocker, {"WEIRD": [0.0, 5.0]})

    assert fetch_quote(Symbol("WEIRD", "Weird")).change_pct is None


def test_fetch_quote_ignores_missing_closes(mocker: MockerFixture) -> None:
    ticker_factory = mocker.patch("app.fetchers.portfolio.yf.Ticker")
    ticker_factory.return_value.history.return_value = pd.DataFrame(
        {"Close": [100.0, 110.0, float("nan")]}
    )

    quote = fetch_quote(Symbol("TSLA", "Tesla"))

    assert quote.close == 110.0
    assert quote.change_pct == pytest.approx(10.0)


def test_fetch_portfolio_prices_isolates_a_failing_symbol(mocker: MockerFixture) -> None:
    def fake_ticker(ticker: str) -> object:
        if ticker == "BROKEN":
            raise RuntimeError("network down")
        handle = mocker.Mock()
        handle.history.return_value = pd.DataFrame({"Close": [100.0, 110.0]})
        return handle

    mocker.patch("app.fetchers.portfolio.yf.Ticker", side_effect=fake_ticker)

    quotes = fetch_portfolio_prices([Symbol("BROKEN", "Broken"), Symbol("TSLA", "Tesla")])

    assert [quote.ticker for quote in quotes] == ["BROKEN", "TSLA"]
    assert quotes[0].close is None
    assert quotes[1].close == 110.0


def test_fetch_portfolio_prices_returns_empty_list_for_empty_portfolio() -> None:
    assert fetch_portfolio_prices([]) == []
