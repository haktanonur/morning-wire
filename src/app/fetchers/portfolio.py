"""Fetch closing price and daily % change for the symbols in the personal portfolio.

Splits file IO (:func:`load_portfolio`) from network IO
(:func:`fetch_portfolio_prices`) so callers can compose them and tests can mock
yfinance without touching the filesystem.
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
    """A single portfolio holding as configured by the user.

    Attributes:
        ticker: Market ticker passed to yfinance, e.g. ``"TSLA"``.
        label: Human-readable name used in the printed brief.
    """

    ticker: str
    label: str


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


def load_portfolio(path: Path | None = None) -> list[Symbol]:
    """Read the configured portfolio symbols from a JSON file.

    Args:
        path: Config file to read. Defaults to ``config/portfolio.json``.

    Returns:
        The configured symbols, in file order.

    Raises:
        PortfolioConfigError: If the file is missing, is not valid JSON, or does
            not match the expected ``{"symbols": [{"ticker", "label"}]}`` shape.
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

    if not isinstance(data, dict) or not isinstance(data.get("symbols"), list):
        raise PortfolioConfigError(
            f"Portfolio config at {config_path} must be an object with a 'symbols' list."
        )

    symbols: list[Symbol] = []
    for entry in data["symbols"]:
        if not isinstance(entry, dict):
            raise PortfolioConfigError(
                f"Portfolio config at {config_path} has a non-object entry in 'symbols'."
            )
        ticker = entry.get("ticker")
        if not isinstance(ticker, str) or not ticker.strip():
            raise PortfolioConfigError(
                f"Portfolio config at {config_path} has an entry with a missing 'ticker'."
            )
        label = entry.get("label")
        symbols.append(
            Symbol(
                ticker=ticker.strip(),
                label=label if isinstance(label, str) and label.strip() else ticker.strip(),
            )
        )
    return symbols


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


def fetch_portfolio_prices(symbols: list[Symbol]) -> list[PortfolioQuote]:
    """Fetch quotes for every configured symbol.

    Args:
        symbols: Holdings to look up, typically from :func:`load_portfolio`.

    Returns:
        One quote per symbol, in the same order. Symbols without data are
        included with ``close`` set to ``None`` rather than being dropped.
    """
    return [fetch_quote(symbol) for symbol in symbols]
