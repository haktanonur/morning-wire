"""Fetch closing price and daily % change for the prices the reader follows.

Two groups, not one list. *Holdings* are what the reader owns; *indices* are
what they watch to read the weather. Mixing them was misleading — an index
sitting in the same column as a holding invites reading it as a position — and
the split costs nothing, because both groups take the same round trip.

Splits file IO (:func:`load_portfolio`) from network IO
(:func:`fetch_portfolio_prices`) so callers can compose them and tests can mock
yfinance without touching the filesystem.

Unlike the other four categories this one is rendered here rather than by the
summarizer, and never reaches the model. Prices are already the answer: there
is nothing to condense, prose about seven numbers is longer than the numbers,
and a model asked to restate a figure can restate it wrong. Nobody reading the
SMS on a phone with no internet could check it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import yfinance as yf

logger = logging.getLogger(__name__)

DEFAULT_PORTFOLIO_PATH = Path(__file__).resolve().parents[3] / "config" / "portfolio.json"

# yfinance returns only trading days, so a 5-day window still yields two closes
# across weekends and single-day market holidays.
_HISTORY_PERIOD = "5d"


class PortfolioConfigError(RuntimeError):
    """Raised when the portfolio config file is missing or malformed."""


@dataclass(frozen=True)
class Symbol:
    """A single price the reader follows, as configured by them.

    Attributes:
        ticker: Market ticker passed to yfinance, e.g. ``"TSLA"``.
        label: Human-readable name used in the printed brief.
    """

    ticker: str
    label: str


@dataclass(frozen=True)
class Portfolio:
    """The two configured groups of symbols.

    Attributes:
        holdings: What the reader owns.
        indices: What the reader watches without holding, e.g. an index or a
            currency pair.
    """

    holdings: list[Symbol]
    indices: list[Symbol]


@dataclass(frozen=True)
class PortfolioQuote:
    """Latest price data for one symbol.

    A quote with ``close`` set to ``None`` means no data was available for that
    symbol; this is not an error and the rest of the portfolio is unaffected.

    Attributes:
        ticker: Market ticker the quote belongs to.
        label: Human-readable name carried over from the config.
        close: Most recent closing price, or ``None`` if unavailable.
        change_pct: Percent change versus the previous close, or ``None`` if it
            could not be computed from the available history.
    """

    ticker: str
    label: str
    close: float | None
    change_pct: float | None


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Quotes for both configured groups, kept apart as they are in the config.

    Attributes:
        holdings: Quotes for what the reader owns.
        indices: Quotes for what the reader watches.
    """

    holdings: list[PortfolioQuote]
    indices: list[PortfolioQuote]


def _parse_group(data: dict[str, object], key: str, config_path: Path) -> list[Symbol]:
    """Read one named list of symbols out of the parsed config.

    A missing key is an empty group rather than an error: a reader who owns
    nothing and only watches indices is a legitimate configuration, and so is
    the reverse. :func:`load_portfolio` rejects the case where *both* are empty,
    which is the one that actually means the file is wrong.
    """
    group = data.get(key, [])
    if not isinstance(group, list):
        raise PortfolioConfigError(f"Portfolio config at {config_path} has a non-list '{key}'.")

    symbols: list[Symbol] = []
    for entry in group:
        if not isinstance(entry, dict):
            raise PortfolioConfigError(
                f"Portfolio config at {config_path} has a non-object entry in '{key}'."
            )
        ticker = entry.get("ticker")
        if not isinstance(ticker, str) or not ticker.strip():
            raise PortfolioConfigError(
                f"Portfolio config at {config_path} has an entry in '{key}' "
                "with a missing 'ticker'."
            )
        label = entry.get("label")
        symbols.append(
            Symbol(
                ticker=ticker.strip(),
                label=label if isinstance(label, str) and label.strip() else ticker.strip(),
            )
        )
    return symbols


def load_portfolio(path: Path | None = None) -> Portfolio:
    """Read the configured holdings and indices from a JSON file.

    Args:
        path: Config file to read. Defaults to ``config/portfolio.json``.

    Returns:
        The two configured groups, each in file order.

    Raises:
        PortfolioConfigError: If the file is missing, is not valid JSON, does not
            match the expected ``{"holdings": [...], "indices": [...]}`` shape,
            or configures no symbols at all.
    """
    config_path = path if path is not None else DEFAULT_PORTFOLIO_PATH

    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PortfolioConfigError(
            f"Portfolio config not found at {config_path}. "
            "Create it with: cp config/portfolio.example.json config/portfolio.json"
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PortfolioConfigError(f"Portfolio config at {config_path} is not valid JSON.") from exc

    if not isinstance(data, dict):
        raise PortfolioConfigError(f"Portfolio config at {config_path} must be a JSON object.")

    portfolio = Portfolio(
        holdings=_parse_group(data, "holdings", config_path),
        indices=_parse_group(data, "indices", config_path),
    )
    # Both groups empty means the file parsed but configures nothing, which for
    # this category is indistinguishable from a silent outage. Better to fail
    # loudly here than to send an empty section every morning.
    if not portfolio.holdings and not portfolio.indices:
        raise PortfolioConfigError(
            f"Portfolio config at {config_path} lists no symbols under 'holdings' or 'indices'."
        )
    return portfolio


def _fetch_recent_closes(ticker: str) -> list[float]:
    """Return the recent daily closing prices for one ticker, oldest first."""
    history = yf.Ticker(ticker).history(period=_HISTORY_PERIOD)
    return [float(close) for close in history["Close"].dropna().tolist()]


def fetch_quote(symbol: Symbol) -> PortfolioQuote:
    """Fetch the latest close and % change for a single symbol.

    Never raises: an unknown ticker or a yfinance/network failure is reported as
    a quote with ``close`` and ``change_pct`` set to ``None``.

    Args:
        symbol: The holding to look up.

    Returns:
        The quote for ``symbol``, possibly with no data.
    """
    try:
        closes = _fetch_recent_closes(symbol.ticker)
    except Exception:
        logger.warning("Price lookup failed for %s; marking as no data.", symbol.ticker)
        return PortfolioQuote(symbol.ticker, symbol.label, close=None, change_pct=None)

    if not closes:
        logger.warning("No price history returned for %s; marking as no data.", symbol.ticker)
        return PortfolioQuote(symbol.ticker, symbol.label, close=None, change_pct=None)

    close = closes[-1]
    change_pct: float | None = None
    if len(closes) >= 2 and closes[-2] != 0:
        change_pct = (close - closes[-2]) / closes[-2] * 100

    return PortfolioQuote(symbol.ticker, symbol.label, close=close, change_pct=change_pct)


def fetch_portfolio_prices(portfolio: Portfolio) -> PortfolioSnapshot:
    """Fetch quotes for every configured symbol, keeping the two groups apart.

    Args:
        portfolio: The configured groups, typically from :func:`load_portfolio`.

    Returns:
        One quote per symbol, in the same order within each group. Symbols
        without data are included with ``close`` set to ``None`` rather than
        being dropped.
    """
    return PortfolioSnapshot(
        holdings=[fetch_quote(symbol) for symbol in portfolio.holdings],
        indices=[fetch_quote(symbol) for symbol in portfolio.indices],
    )


def _format_price(close: float) -> str:
    """Render a price at a precision that suits its magnitude.

    A currency pair and an index cannot share one format: ``1.14`` loses the
    movement EUR/USD is read for, while ``30608.1309`` is noise. Four decimals
    below ten, two above, which covers everything from a parity to an index
    without a per-symbol setting to keep in the config.
    """
    return f"{close:.4f}" if abs(close) < 10 else f"{close:.2f}"


def _format_quote(quote: PortfolioQuote) -> str:
    """Render one quote as a single SMS line."""
    if quote.close is None:
        return f"{quote.label}: veri yok"
    if quote.change_pct is None:
        return f"{quote.label} {_format_price(quote.close)}"
    return f"{quote.label} {_format_price(quote.close)} {quote.change_pct:+.2f}%"


def render_portfolio(snapshot: PortfolioSnapshot) -> str:
    """Render the snapshot as the body of one SMS.

    Turkish, like every other body in the brief, and labelled per group so that
    an index is not read as a position. A group with nothing configured is left
    out entirely rather than printed as an empty heading.
    """
    blocks = [
        f"{heading}\n" + "\n".join(_format_quote(quote) for quote in quotes)
        for heading, quotes in (("Portfoy:", snapshot.holdings), ("Piyasa:", snapshot.indices))
        if quotes
    ]
    return "\n".join(blocks)
