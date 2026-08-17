"""CLI entrypoint: fetch, summarize and print all four categories.

Run with ``python -m app.main``. Each category is fetched and summarized inside
its own try/except, so one dead data source or one failed API call costs that
section only — the other three still print. See ``PLAN.md`` §6 for the output
format and §9 for the error-handling strategy.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass

from app.fetchers.general_news import fetch_general_news
from app.fetchers.market_news import fetch_market_news
from app.fetchers.portfolio import fetch_portfolio_prices, load_portfolio
from app.fetchers.sports import fetch_sports
from app.summarizer import (
    summarize_markets,
    summarize_news,
    summarize_portfolio,
    summarize_sports,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Section:
    """One rendered category of the briefing."""

    heading: str
    body: str


def _markets() -> str:
    return summarize_markets(fetch_market_news())


def _portfolio() -> str:
    return summarize_portfolio(fetch_portfolio_prices(load_portfolio()))


def _news() -> str:
    return summarize_news(fetch_general_news())


def _sports() -> str:
    return summarize_sports(fetch_sports())


# Order matches PLAN.md §6, which is also the Phase 2 SMS send order.
CATEGORIES: tuple[tuple[str, Callable[[], str]], ...] = (
    ("MARKETS", _markets),
    ("PORTFOLIO", _portfolio),
    ("NEWS", _news),
    ("SPORTS", _sports),
)


def build_section(heading: str, produce: Callable[[], str]) -> Section:
    """Run one category, converting any failure into an ``[unavailable: ...]`` body.

    This is the error-isolation boundary: nothing raised by a fetcher or the
    summarizer is allowed past it.
    """
    try:
        return Section(heading=heading, body=produce())
    except Exception as exc:
        logger.warning("Category %s failed.", heading, exc_info=True)
        reason = str(exc) or type(exc).__name__
        return Section(heading=heading, body=f"[unavailable: {reason}]")


def build_report() -> list[Section]:
    """Fetch and summarize every category, isolating failures per section."""
    return [build_section(heading, produce) for heading, produce in CATEGORIES]


def render(sections: list[Section]) -> str:
    """Format sections into the terminal report described in PLAN.md §6."""
    return "\n\n".join(f"=== {section.heading} ===\n{section.body}" for section in sections)


def main() -> None:
    """Print the full briefing to stdout.

    Warnings go to stderr so the report on stdout stays pipeable.
    """
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    print(render(build_report()))


if __name__ == "__main__":
    main()
