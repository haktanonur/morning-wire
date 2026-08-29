"""CLI entrypoint: fetch, summarize, print and send all four categories.

Run with ``python -m app.main`` to send the briefing as SMS, or
``python -m app.main --dry-run`` to print it and send nothing. Sending is the
default because the scheduled run is the real use of this program and a cron
takes no arguments; ``--dry-run`` is what a developer types.

Each category is fetched and summarized inside its own try/except, so one dead
data source or one failed API call costs that section only — the other three
still print and still send. See ``PLAN.md`` §6 for the output format and §9 for
the error-handling strategy.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.fetchers.general_news import fetch_general_news
from app.fetchers.market_news import fetch_market_news
from app.fetchers.portfolio import fetch_portfolio_prices, load_portfolio
from app.fetchers.sports import fetch_sports
from app.sender import SendOutcome, send_report
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


def delivery_summary(outcomes: Sequence[SendOutcome]) -> str:
    """One line describing what the relay took.

    "Accepted", not "delivered": the relay answers the same way whether the
    phone sent the SMS or was switched off (see ``sender.py``).
    """
    refused = [outcome.heading for outcome in outcomes if not outcome.accepted]
    accepted = len(outcomes) - len(refused)
    if not refused:
        return f"SMS relay accepted all {accepted} categories."
    return f"SMS relay accepted {accepted}/{len(outcomes)}; refused: {', '.join(refused)}."


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the command line."""
    parser = argparse.ArgumentParser(
        prog="python -m app.main",
        description="Fetch, summarize and send the daily briefing.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the briefing to stdout and send no SMS.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Print the full briefing to stdout and, unless ``--dry-run``, send it.

    The report is printed before anything is sent, so a failure in delivery
    still leaves the briefing readable.

    Warnings and the delivery summary go to stderr so the report on stdout stays
    pipeable.

    Returns:
        ``0`` if every category reached the relay (or nothing was sent), ``1``
        if any category did not. The exit code is the only failure signal a
        scheduled run has; without it the job would go green while the owner's
        phone stayed silent.
    """
    args = parse_args(argv)
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    sections = build_report()
    print(render(sections))
    if args.dry_run:
        return 0

    outcomes = send_report((section.heading, section.body) for section in sections)
    print(delivery_summary(outcomes), file=sys.stderr)
    return 0 if all(outcome.accepted for outcome in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
