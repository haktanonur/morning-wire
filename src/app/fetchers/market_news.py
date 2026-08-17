"""Fetch global market headlines from the Finnhub market news API.

Covers PLAN.md category 1 (economy and global markets). Alpha Vantage is listed
as a possible fallback source in ``docs/data-sources.md`` but is deliberately not
implemented here; this module intentionally has a single source.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests

from app.config import load_finnhub_settings

logger = logging.getLogger(__name__)

FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/news"
DEFAULT_LIMIT = 10
REQUEST_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class Headline:
    """A single market news story.

    Attributes:
        title: Story headline as reported by the publisher.
        source: Publisher name, e.g. ``"Reuters"``.
        url: Link to the full story.
        summary: Publisher's short blurb; may be an empty string.
        published_at: Publication time in UTC, or ``None`` if Finnhub omitted or
            malformed the timestamp.
    """

    title: str
    source: str
    url: str
    summary: str
    published_at: datetime | None


def _parse_published_at(raw_timestamp: Any) -> datetime | None:
    """Convert Finnhub's unix timestamp into an aware UTC datetime, or None."""
    if not isinstance(raw_timestamp, int | float) or isinstance(raw_timestamp, bool):
        return None
    try:
        return datetime.fromtimestamp(raw_timestamp, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _parse_article(raw: Any) -> Headline | None:
    """Build a Headline from one Finnhub article, or None if it is unusable.

    A story with no title carries no value for the summarizer, so it is dropped
    rather than surfaced as an empty entry.
    """
    if not isinstance(raw, dict):
        return None

    title = raw.get("headline")
    if not isinstance(title, str) or not title.strip():
        return None

    def _text(key: str) -> str:
        value = raw.get(key)
        return value.strip() if isinstance(value, str) else ""

    return Headline(
        title=title.strip(),
        source=_text("source"),
        url=_text("url"),
        summary=_text("summary"),
        published_at=_parse_published_at(raw.get("datetime")),
    )


def fetch_market_news(limit: int = DEFAULT_LIMIT) -> list[Headline]:
    """Fetch the latest global market headlines.

    Never raises. A missing API key, a network failure, an HTTP error, or a
    malformed response all produce an empty list plus a logged warning, so the
    markets category degrades to "data unavailable" without affecting the other
    three categories.

    Args:
        limit: Maximum number of headlines to return. Values below 1 yield an
            empty list.

    Returns:
        Up to ``limit`` headlines, newest first as returned by Finnhub.
    """
    if limit < 1:
        return []

    try:
        settings = load_finnhub_settings()
        response = requests.get(
            FINNHUB_NEWS_URL,
            params={"category": "general"},
            # Header auth rather than a `token` query param: request URLs show up
            # in exception messages and logs, and the key must never leak there.
            headers={"X-Finnhub-Token": settings.api_key},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.warning("Market news fetch failed (%s); returning no headlines.", type(exc).__name__)
        return []

    if not isinstance(payload, list):
        logger.warning("Market news response was not a list; returning no headlines.")
        return []

    headlines = [parsed for raw in payload if (parsed := _parse_article(raw)) is not None]
    if not headlines:
        logger.warning("Market news response contained no usable headlines.")
    return headlines[:limit]
