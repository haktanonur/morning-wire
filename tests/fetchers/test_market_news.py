import logging
from datetime import UTC, datetime
from typing import Any

import pytest
import requests
import responses

from app.fetchers.market_news import (
    FINNHUB_NEWS_URL,
    Headline,
    fetch_market_news,
)

API_KEY = "fake-finnhub-key-abc123"


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test a known key so nothing can fall through to the real .env."""
    monkeypatch.setenv("FINNHUB_API_KEY", API_KEY)


def _article(**overrides: Any) -> dict[str, Any]:
    article: dict[str, Any] = {
        "headline": "Fed holds rates steady",
        "source": "Reuters",
        "url": "https://example.com/fed",
        "summary": "The Federal Reserve left rates unchanged.",
        "datetime": 1700000000,
    }
    article.update(overrides)
    return article


@responses.activate
def test_fetch_market_news_returns_parsed_headlines() -> None:
    responses.add(responses.GET, FINNHUB_NEWS_URL, json=[_article()], status=200)

    assert fetch_market_news() == [
        Headline(
            title="Fed holds rates steady",
            source="Reuters",
            url="https://example.com/fed",
            summary="The Federal Reserve left rates unchanged.",
            published_at=datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC),
        )
    ]


@responses.activate
def test_fetch_market_news_sends_key_as_header_not_query_param() -> None:
    responses.add(responses.GET, FINNHUB_NEWS_URL, json=[_article()], status=200)

    fetch_market_news()

    request = responses.calls[0].request
    assert request.headers["X-Finnhub-Token"] == API_KEY
    assert API_KEY not in str(request.url)
    assert "category=general" in str(request.url)


@responses.activate
def test_fetch_market_news_respects_limit() -> None:
    payload = [_article(headline=f"Story {index}") for index in range(25)]
    responses.add(responses.GET, FINNHUB_NEWS_URL, json=payload, status=200)

    headlines = fetch_market_news(limit=3)

    assert [headline.title for headline in headlines] == ["Story 0", "Story 1", "Story 2"]


def test_fetch_market_news_returns_empty_list_for_non_positive_limit() -> None:
    assert fetch_market_news(limit=0) == []


@responses.activate
def test_fetch_market_news_returns_empty_list_on_http_error() -> None:
    responses.add(responses.GET, FINNHUB_NEWS_URL, json={"error": "rate limit"}, status=429)

    assert fetch_market_news() == []


@responses.activate
def test_fetch_market_news_returns_empty_list_on_connection_error() -> None:
    responses.add(responses.GET, FINNHUB_NEWS_URL, body=requests.ConnectionError("network down"))

    assert fetch_market_news() == []


@responses.activate
def test_fetch_market_news_returns_empty_list_on_invalid_json() -> None:
    responses.add(responses.GET, FINNHUB_NEWS_URL, body="<html>oops</html>", status=200)

    assert fetch_market_news() == []


@responses.activate
def test_fetch_market_news_returns_empty_list_on_non_list_payload() -> None:
    responses.add(responses.GET, FINNHUB_NEWS_URL, json={"s": "no_data"}, status=200)

    assert fetch_market_news() == []


def test_fetch_market_news_returns_empty_list_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)

    assert fetch_market_news() == []


@responses.activate
def test_fetch_market_news_skips_articles_without_a_headline() -> None:
    responses.add(
        responses.GET,
        FINNHUB_NEWS_URL,
        json=[_article(headline=""), "not-an-object", _article(), {"no": "headline"}],
        status=200,
    )

    headlines = fetch_market_news()

    assert [headline.title for headline in headlines] == ["Fed holds rates steady"]


@responses.activate
def test_fetch_market_news_warns_when_no_usable_headlines(
    caplog: pytest.LogCaptureFixture,
) -> None:
    responses.add(responses.GET, FINNHUB_NEWS_URL, json=[], status=200)

    with caplog.at_level(logging.WARNING):
        assert fetch_market_news() == []

    assert "no usable headlines" in caplog.text


@responses.activate
def test_fetch_market_news_defaults_missing_optional_fields_to_empty_strings() -> None:
    responses.add(responses.GET, FINNHUB_NEWS_URL, json=[{"headline": "Bare story"}], status=200)

    assert fetch_market_news() == [
        Headline(title="Bare story", source="", url="", summary="", published_at=None)
    ]


@responses.activate
@pytest.mark.parametrize("timestamp", ["1700000000", None, True, 10**20])
def test_fetch_market_news_tolerates_unusable_timestamp(timestamp: Any) -> None:
    responses.add(responses.GET, FINNHUB_NEWS_URL, json=[_article(datetime=timestamp)], status=200)

    headlines = fetch_market_news()

    assert headlines[0].published_at is None


@responses.activate
def test_fetch_market_news_warning_does_not_leak_the_api_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 401 from requests puts the request URL in the exception; the key must not follow."""
    responses.add(responses.GET, FINNHUB_NEWS_URL, json={"error": "invalid key"}, status=401)

    with caplog.at_level(logging.WARNING):
        assert fetch_market_news() == []

    assert caplog.records, "expected a warning to be logged"
    assert API_KEY not in caplog.text
