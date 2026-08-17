import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from pytest_mock import MockerFixture

from app.fetchers.general_news import (
    FEEDS,
    REGION_TR,
    REGION_WORLD,
    Article,
    NewsFeed,
    fetch_feed,
    fetch_general_news,
)

TR_FEED = NewsFeed(name="Test TR", url="https://example.com/tr.rss", region=REGION_TR)
WORLD_FEED = NewsFeed(name="Test World", url="https://example.com/world.rss", region=REGION_WORLD)


def _entry(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "title": "Enflasyon verisi açıklandı",
        "link": "https://example.com/story",
        "summary": "TÜİK aylık enflasyon rakamlarını yayımladı.",
        "published_parsed": (2026, 8, 17, 6, 30, 0, 0, 229, 0),
    }
    entry.update(overrides)
    return entry


def _mock_parse(mocker: MockerFixture, result_by_url: dict[str, Any]) -> Any:
    """Patch feedparser.parse so no test can reach the network."""
    return mocker.patch(
        "app.fetchers.general_news.feedparser.parse",
        side_effect=lambda url: result_by_url[url],
    )


def _feed_result(entries: list[Any], status: int = 200, **extra: Any) -> Any:
    """Stand in for the attribute-style result object feedparser.parse returns."""
    return SimpleNamespace(entries=entries, status=status, **extra)


def test_default_feeds_cover_tr_and_world() -> None:
    regions = {feed.region for feed in FEEDS}
    assert regions == {REGION_TR, REGION_WORLD}
    assert all(feed.url.startswith("https://") for feed in FEEDS)


def test_fetch_feed_parses_entries(mocker: MockerFixture) -> None:
    _mock_parse(mocker, {TR_FEED.url: _feed_result([_entry()])})

    assert fetch_feed(TR_FEED) == [
        Article(
            title="Enflasyon verisi açıklandı",
            source="Test TR",
            url="https://example.com/story",
            summary="TÜİK aylık enflasyon rakamlarını yayımladı.",
            published_at=datetime(2026, 8, 17, 6, 30, tzinfo=UTC),
            region=REGION_TR,
        )
    ]


def test_fetch_feed_respects_limit(mocker: MockerFixture) -> None:
    entries = [_entry(title=f"Haber {index}") for index in range(20)]
    _mock_parse(mocker, {TR_FEED.url: _feed_result(entries)})

    assert [article.title for article in fetch_feed(TR_FEED, limit=3)] == [
        "Haber 0",
        "Haber 1",
        "Haber 2",
    ]


def test_fetch_feed_returns_empty_list_for_non_positive_limit(mocker: MockerFixture) -> None:
    parse = _mock_parse(mocker, {})

    assert fetch_feed(TR_FEED, limit=0) == []
    parse.assert_not_called()


def test_fetch_feed_returns_empty_list_on_http_error(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    _mock_parse(mocker, {TR_FEED.url: _feed_result([_entry()], status=404)})

    with caplog.at_level(logging.WARNING):
        assert fetch_feed(TR_FEED) == []

    assert "HTTP 404" in caplog.text


def test_fetch_feed_returns_empty_list_when_parse_raises(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    mocker.patch(
        "app.fetchers.general_news.feedparser.parse",
        side_effect=OSError("name resolution failed"),
    )

    with caplog.at_level(logging.WARNING):
        assert fetch_feed(TR_FEED) == []

    assert "OSError" in caplog.text


def test_fetch_feed_returns_empty_list_when_feed_is_unparseable(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """A dead endpoint gives feedparser no entries and a bozo_exception, not a raise."""
    _mock_parse(
        mocker,
        {TR_FEED.url: _feed_result([], status=200, bozo=1, bozo_exception=ValueError("not xml"))},
    )

    with caplog.at_level(logging.WARNING):
        assert fetch_feed(TR_FEED) == []

    assert "no usable articles" in caplog.text
    assert "ValueError" in caplog.text


def test_fetch_feed_skips_entries_without_a_title(mocker: MockerFixture) -> None:
    _mock_parse(
        mocker,
        {TR_FEED.url: _feed_result([_entry(title=""), _entry(title="   "), _entry()])},
    )

    assert [article.title for article in fetch_feed(TR_FEED)] == ["Enflasyon verisi açıklandı"]


def test_fetch_feed_defaults_missing_optional_fields(mocker: MockerFixture) -> None:
    _mock_parse(mocker, {TR_FEED.url: _feed_result([{"title": "Sadece başlık"}])})

    assert fetch_feed(TR_FEED) == [
        Article(
            title="Sadece başlık",
            source="Test TR",
            url="",
            summary="",
            published_at=None,
            region=REGION_TR,
        )
    ]


@pytest.mark.parametrize("published", [None, "2026-08-17", (2026,), (9999999, 1, 1, 0, 0, 0)])
def test_fetch_feed_tolerates_unusable_timestamp(mocker: MockerFixture, published: Any) -> None:
    _mock_parse(mocker, {TR_FEED.url: _feed_result([_entry(published_parsed=published)])})

    assert fetch_feed(TR_FEED)[0].published_at is None


def test_fetch_feed_handles_missing_status_attribute(mocker: MockerFixture) -> None:
    """feedparser omits `status` entirely for non-HTTP inputs; that is not an error."""
    _mock_parse(mocker, {TR_FEED.url: SimpleNamespace(entries=[_entry()])})

    assert len(fetch_feed(TR_FEED)) == 1


def test_fetch_general_news_groups_feeds_in_order(mocker: MockerFixture) -> None:
    _mock_parse(
        mocker,
        {
            TR_FEED.url: _feed_result([_entry(title="TR haber")]),
            WORLD_FEED.url: _feed_result([_entry(title="World story")]),
        },
    )

    articles = fetch_general_news(feeds=(TR_FEED, WORLD_FEED))

    assert [article.title for article in articles] == ["TR haber", "World story"]
    assert [article.region for article in articles] == [REGION_TR, REGION_WORLD]


def test_fetch_general_news_isolates_a_broken_feed(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    def parse(url: str) -> Any:
        if url == TR_FEED.url:
            raise OSError("unreachable")
        return _feed_result([_entry(title="World story")])

    mocker.patch("app.fetchers.general_news.feedparser.parse", side_effect=parse)

    with caplog.at_level(logging.WARNING):
        articles = fetch_general_news(feeds=(TR_FEED, WORLD_FEED))

    assert [article.title for article in articles] == ["World story"]
    assert "Test TR" in caplog.text


def test_fetch_general_news_returns_empty_list_when_every_feed_fails(
    mocker: MockerFixture,
) -> None:
    mocker.patch("app.fetchers.general_news.feedparser.parse", side_effect=OSError("down"))

    assert fetch_general_news(feeds=(TR_FEED, WORLD_FEED)) == []
