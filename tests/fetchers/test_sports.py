import logging
from datetime import date
from typing import Any

import pytest
import requests
import responses

from app.fetchers.sports import (
    FOOTBALL_MATCHES_URL,
    MatchResult,
    fetch_sports,
)

API_KEY = "fake-football-data-key-abc123"
TODAY = date(2026, 8, 17)


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test a known key so nothing can fall through to the real .env."""
    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", API_KEY)


def _match(**overrides: Any) -> dict[str, Any]:
    match: dict[str, Any] = {
        "utcDate": "2026-08-16T14:00:00Z",
        "status": "FINISHED",
        "competition": {"name": "Premier League", "code": "PL"},
        "homeTeam": {"name": "Arsenal FC"},
        "awayTeam": {"name": "Chelsea FC"},
        "score": {"winner": "HOME_TEAM", "fullTime": {"home": 2, "away": 1}},
    }
    match.update(overrides)
    return match


@responses.activate
def test_fetch_sports_returns_parsed_matches() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, json={"matches": [_match()]}, status=200)

    assert fetch_sports(today=TODAY) == (
        MatchResult(
            competition="Premier League",
            home_team="Arsenal FC",
            away_team="Chelsea FC",
            home_score=2,
            away_score=1,
            played_on=date(2026, 8, 16),
        ),
    )


@responses.activate
def test_fetch_sports_sends_key_as_header_not_query_param() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, json={"matches": []}, status=200)

    fetch_sports(today=TODAY)

    request = responses.calls[0].request
    assert request.headers["X-Auth-Token"] == API_KEY
    assert API_KEY not in str(request.url)


@responses.activate
def test_fetch_sports_requests_the_lookback_window() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, json={"matches": []}, status=200)

    fetch_sports(today=TODAY, lookback_days=2)

    url = str(responses.calls[0].request.url)
    assert "dateFrom=2026-08-15" in url
    assert "dateTo=2026-08-17" in url
    assert "competitions=PL%2CPD%2CSA" in url


@responses.activate
def test_fetch_sports_skips_matches_that_are_not_finished() -> None:
    responses.add(
        responses.GET,
        FOOTBALL_MATCHES_URL,
        json={"matches": [_match(status="SCHEDULED"), _match(status="POSTPONED"), _match()]},
        status=200,
    )

    assert len(fetch_sports(today=TODAY)) == 1


@responses.activate
@pytest.mark.parametrize(
    "broken",
    [
        {"score": {"fullTime": {"home": None, "away": None}}},
        {"score": {"fullTime": {}}},
        {"score": {}},
        {"homeTeam": {}},
        {"homeTeam": "Arsenal FC"},
        {"awayTeam": {"name": ""}},
        {"utcDate": "not-a-date"},
        {"utcDate": None},
    ],
)
def test_fetch_sports_skips_unusable_matches(broken: dict[str, Any]) -> None:
    responses.add(
        responses.GET,
        FOOTBALL_MATCHES_URL,
        json={"matches": [_match(**broken), "not-an-object", _match()]},
        status=200,
    )

    matches = fetch_sports(today=TODAY)

    assert [match.home_team for match in matches] == ["Arsenal FC"]


@responses.activate
def test_fetch_sports_returns_empty_on_http_error() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, json={"message": "rate limit"}, status=429)

    assert fetch_sports(today=TODAY) == ()


@responses.activate
def test_fetch_sports_returns_empty_on_connection_error() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, body=requests.ConnectionError("down"))

    assert fetch_sports(today=TODAY) == ()


@responses.activate
def test_fetch_sports_returns_empty_on_invalid_json() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, body="<html>oops</html>", status=200)

    assert fetch_sports(today=TODAY) == ()


@responses.activate
def test_fetch_sports_returns_empty_on_payload_without_matches() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, json={"errorCode": 400}, status=200)

    assert fetch_sports(today=TODAY) == ()


def test_fetch_sports_returns_empty_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOOTBALL_DATA_API_KEY", raising=False)

    assert fetch_sports(today=TODAY) == ()


@responses.activate
def test_fetch_sports_returns_empty_in_the_off_season() -> None:
    """No fixtures is a normal outcome, not an error."""
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, json={"matches": []}, status=200)

    assert fetch_sports(today=TODAY) == ()


@responses.activate
def test_fetch_sports_warning_does_not_leak_the_api_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 403 puts the request URL into the exception; the key must not follow."""
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, json={"message": "forbidden"}, status=403)

    with caplog.at_level(logging.WARNING):
        assert fetch_sports(today=TODAY) == ()

    assert caplog.records, "expected a warning to be logged"
    assert API_KEY not in caplog.text
