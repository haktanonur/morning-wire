import json
from pathlib import Path

import pandas as pd
import pytest
from pytest_mock import MockerFixture

from app.fetchers.portfolio import (
    DEFAULT_PORTFOLIO_PATH,
    Portfolio,
    PortfolioConfigError,
    PortfolioQuote,
    PortfolioSnapshot,
    Symbol,
    fetch_portfolio_prices,
    fetch_quote,
    load_portfolio,
    render_portfolio,
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


def test_load_portfolio_reads_both_groups_in_order(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path,
        {
            "holdings": [
                {"ticker": "GC=F", "label": "Gold"},
                {"ticker": "SI=F", "label": "Silver"},
            ],
            "indices": [{"ticker": "^GSPC", "label": "S&P 500"}],
        },
    )

    portfolio = load_portfolio(config_path)

    assert portfolio.holdings == [Symbol("GC=F", "Gold"), Symbol("SI=F", "Silver")]
    assert portfolio.indices == [Symbol("^GSPC", "S&P 500")]


@pytest.mark.parametrize("present", ["holdings", "indices"])
def test_load_portfolio_allows_either_group_to_be_absent(tmp_path: Path, present: str) -> None:
    """Owning nothing and watching nothing are both legitimate; only neither is not."""
    config_path = _write_config(tmp_path, {present: [{"ticker": "GC=F"}]})

    portfolio = load_portfolio(config_path)

    assert getattr(portfolio, present) == [Symbol("GC=F", "GC=F")]


def test_load_portfolio_defaults_label_to_ticker(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, {"holdings": [{"ticker": " TSLA "}]})

    assert load_portfolio(config_path).holdings == [Symbol("TSLA", "TSLA")]


def test_load_portfolio_raises_when_file_missing(tmp_path: Path) -> None:
    with pytest.raises(PortfolioConfigError, match="cp config/portfolio.example.json"):
        load_portfolio(tmp_path / "does-not-exist.json")


def test_load_portfolio_raises_when_json_invalid(tmp_path: Path) -> None:
    config_path = tmp_path / "portfolio.json"
    config_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(PortfolioConfigError, match="not valid JSON"):
        load_portfolio(config_path)


def test_load_portfolio_raises_when_top_level_is_not_an_object(tmp_path: Path) -> None:
    with pytest.raises(PortfolioConfigError, match="must be a JSON object"):
        load_portfolio(_write_config(tmp_path, []))


@pytest.mark.parametrize("payload", [{}, {"holdings": [], "indices": []}])
def test_load_portfolio_raises_when_nothing_is_configured(tmp_path: Path, payload: object) -> None:
    """A file that parses but lists nothing looks exactly like an outage in the SMS."""
    with pytest.raises(PortfolioConfigError, match="lists no symbols"):
        load_portfolio(_write_config(tmp_path, payload))


@pytest.mark.parametrize("group", ["holdings", "indices"])
def test_load_portfolio_raises_when_a_group_is_not_a_list(tmp_path: Path, group: str) -> None:
    with pytest.raises(PortfolioConfigError, match=f"non-list '{group}'"):
        load_portfolio(_write_config(tmp_path, {group: "TSLA"}))


def test_load_portfolio_raises_when_entry_is_not_an_object(tmp_path: Path) -> None:
    with pytest.raises(PortfolioConfigError, match="non-object entry"):
        load_portfolio(_write_config(tmp_path, {"holdings": ["TSLA"]}))


@pytest.mark.parametrize("entry", [{"label": "No ticker"}, {"ticker": ""}, {"ticker": 123}])
def test_load_portfolio_raises_when_ticker_missing(tmp_path: Path, entry: object) -> None:
    with pytest.raises(PortfolioConfigError, match="missing 'ticker'"):
        load_portfolio(_write_config(tmp_path, {"holdings": [entry]}))


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

    snapshot = fetch_portfolio_prices(
        Portfolio(holdings=[Symbol("BROKEN", "Broken")], indices=[Symbol("TSLA", "Tesla")])
    )

    assert snapshot.holdings[0] == PortfolioQuote("BROKEN", "Broken", None, None)
    assert snapshot.indices[0].close == 110.0


def test_fetch_portfolio_prices_returns_empty_groups_for_an_empty_portfolio() -> None:
    assert fetch_portfolio_prices(Portfolio(holdings=[], indices=[])) == PortfolioSnapshot([], [])


# --- rendering --------------------------------------------------------------


def test_render_portfolio_labels_each_group() -> None:
    """The whole point of the split: an index must not read as a position."""
    body = render_portfolio(
        PortfolioSnapshot(
            holdings=[PortfolioQuote("GC=F", "Ons altin", 4321.2, 0.54)],
            indices=[PortfolioQuote("XU100.IS", "BIST 100", 12899.4, -0.09)],
        )
    )

    assert body == "Portfoy:\nOns altin 4321.20 +0.54%\nPiyasa:\nBIST 100 12899.40 -0.09%"


def test_render_portfolio_omits_a_group_that_is_not_configured() -> None:
    body = render_portfolio(
        PortfolioSnapshot(holdings=[PortfolioQuote("GC=F", "Ons altin", 4321.2, 0.54)], indices=[])
    )

    assert "Piyasa:" not in body


def test_render_portfolio_keeps_four_decimals_below_ten() -> None:
    """EUR/USD is read for movement that two decimals would round away."""
    body = render_portfolio(
        PortfolioSnapshot(
            holdings=[], indices=[PortfolioQuote("EURUSD=X", "EUR/USD", 1.14003, 0.2)]
        )
    )

    assert "EUR/USD 1.1400 +0.20%" in body


def test_render_portfolio_names_a_symbol_with_no_data() -> None:
    """Dropping it silently would look identical to never having configured it."""
    body = render_portfolio(
        PortfolioSnapshot(holdings=[PortfolioQuote("GC=F", "Ons altin", None, None)], indices=[])
    )

    assert "Ons altin: veri yok" in body


def test_render_portfolio_prints_a_price_that_has_no_change_yet() -> None:
    """A first-ever close has no previous day to compare against, but is still a price."""
    body = render_portfolio(
        PortfolioSnapshot(holdings=[PortfolioQuote("GC=F", "Ons altin", 4321.2, None)], indices=[])
    )

    assert body == "Portfoy:\nOns altin 4321.20"
