"""Fetch Turkish and global current-affairs headlines from public RSS feeds.

Covers PLAN.md category 3. RSS is used rather than a news API because it needs
no key and no vendor account, which makes it the most durable source in the
project (see ``docs/data-sources.md``).

Note: ``PLAN.md`` and ``docs/data-sources.md`` still name Reuters World News as a
source, but Reuters retired its public RSS feeds and the endpoint now returns no
entries. BBC World replaces it as the global feed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import feedparser

logger = logging.getLogger(__name__)

REGION_TR = "TR"
REGION_WORLD = "WORLD"

DEFAULT_LIMIT_PER_FEED = 8


@dataclass(frozen=True)
class NewsFeed:
    """An RSS source to poll.

    Attributes:
        name: Publisher name shown alongside the headline.
        url: RSS endpoint.
        region: Either ``"TR"`` or ``"WORLD"``, so the summarizer can keep the
            Turkish and global halves of the category apart.
    """

    name: str
    url: str
    region: str


FEEDS: tuple[NewsFeed, ...] = (
    NewsFeed(
        name="Anadolu Ajansı (Gündem)",
        url="https://www.aa.com.tr/tr/rss/default?cat=guncel",
        region=REGION_TR,
    ),
    NewsFeed(
        name="Anadolu Ajansı (Ekonomi)",
        url="https://www.aa.com.tr/tr/rss/default?cat=ekonomi",
        region=REGION_TR,
    ),
    NewsFeed(
        name="BBC World",
        url="https://feeds.bbci.co.uk/news/world/rss.xml",
        region=REGION_WORLD,
    ),
)


@dataclass(frozen=True)
class Article:
    """A single news story.

    Attributes:
        title: Story headline.
        source: Name of the feed it came from.
        url: Link to the full story; may be an empty string.
        summary: Publisher's blurb; may be an empty string.
        published_at: Publication time in UTC, or ``None`` if the feed omitted or
            malformed it.
        region: ``"TR"`` or ``"WORLD"``, inherited from the feed.
    """

    title: str
    source: str
    url: str
    summary: str
    published_at: datetime | None
    region: str


def _parse_published_at(raw_struct_time: Any) -> datetime | None:
    """Convert feedparser's ``published_parsed`` struct_time into an aware UTC datetime."""
    if raw_struct_time is None:
        return None
    try:
        year, month, day, hour, minute, second = raw_struct_time[:6]
        return datetime(year, month, day, hour, minute, second, tzinfo=UTC)
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_entry(raw: Any, feed: NewsFeed) -> Article | None:
    """Build an Article from one RSS entry, or None if it has no usable title."""

    def _text(key: str) -> str:
        value = raw.get(key) if hasattr(raw, "get") else None
        return value.strip() if isinstance(value, str) else ""

    title = _text("title")
    if not title:
        return None

    published_raw = raw.get("published_parsed") if hasattr(raw, "get") else None
    return Article(
        title=title,
        source=feed.name,
        url=_text("link"),
        summary=_text("summary"),
        published_at=_parse_published_at(published_raw),
        region=feed.region,
    )


def fetch_feed(feed: NewsFeed, limit: int = DEFAULT_LIMIT_PER_FEED) -> list[Article]:
    """Fetch articles from a single RSS feed.

    Never raises. An unreachable host, an HTTP error, or unparseable XML all
    produce an empty list plus a logged warning, so one dead feed cannot take
    down the others.

    Args:
        feed: The source to poll.
        limit: Maximum number of articles to take from this feed.

    Returns:
        Up to ``limit`` articles, in the order the feed published them.
    """
    if limit < 1:
        return []

    try:
        parsed = feedparser.parse(feed.url)
    except Exception as exc:
        logger.warning("Feed %s failed to parse (%s); skipping.", feed.name, type(exc).__name__)
        return []

    # feedparser reports transport failures through `status`/`bozo` instead of
    # raising, so both have to be inspected explicitly.
    status = getattr(parsed, "status", None)
    if isinstance(status, int) and status >= 400:
        logger.warning("Feed %s returned HTTP %s; skipping.", feed.name, status)
        return []

    entries = getattr(parsed, "entries", [])
    articles = [article for raw in entries if (article := _parse_entry(raw, feed)) is not None]

    if not articles:
        # `bozo` is also set for feeds that are merely untidy, so it is only
        # worth reporting when nothing usable came back at all.
        reason = type(getattr(parsed, "bozo_exception", None)).__name__
        logger.warning("Feed %s returned no usable articles (%s).", feed.name, reason)

    return articles[:limit]


def fetch_general_news(
    limit_per_feed: int = DEFAULT_LIMIT_PER_FEED,
    feeds: tuple[NewsFeed, ...] = FEEDS,
) -> list[Article]:
    """Fetch Turkish and global headlines from every configured feed.

    Never raises. Feeds are polled independently, so a broken source only costs
    its own headlines.

    Args:
        limit_per_feed: Maximum number of articles to take from each feed.
        feeds: Sources to poll. Defaults to :data:`FEEDS`.

    Returns:
        Articles grouped in feed order, Turkish sources first.
    """
    articles: list[Article] = []
    for feed in feeds:
        articles.extend(fetch_feed(feed, limit=limit_per_feed))
    return articles
