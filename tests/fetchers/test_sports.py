import logging
from datetime import date
from typing import Any

import pytest
import requests
import responses

from app.fetchers.sports import (
    F1_LAST_RACE_URL,
    FOOTBALL_MATCHES_URL,
    DriverResult,
    MatchResult,
    RaceResult,
    SportsReport,
    fetch_f1_result,
    fetch_football_results,
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


def _race(**overrides: Any) -> dict[str, Any]:
    race: dict[str, Any] = {
        "season": "2026",
        "round": "13",
        "raceName": "Hungarian Grand Prix",
        "date": "2026-08-16",
        "Results": [
            {
                "position": "2",
                "Driver": {"givenName": "Oscar", "familyName": "Piastri"},
                "Constructor": {"name": "McLaren"},
            },
            {
                "position": "1",
                "Driver": {"givenName": "Lando", "familyName": "Norris"},
                "Constructor": {"name": "McLaren"},
            },
            {
                "position": "3",
                "Driver": {"givenName": "Max", "familyName": "Verstappen"},
                "Constructor": {"name": "Red Bull"},
            },
            {
                "position": "4",
                "Driver": {"givenName": "George", "familyName": "Russell"},
                "Constructor": {"name": "Mercedes"},
            },
        ],
    }
    race.update(overrides)
    return race


def _f1_payload(*races: dict[str, Any]) -> dict[str, Any]:
    return {"MRData": {"RaceTable": {"season": "2026", "Races": list(races)}}}


# --- football ---------------------------------------------------------------


@responses.activate
def test_fetch_football_results_returns_parsed_matches() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, json={"matches": [_match()]}, status=200)

    assert fetch_football_results(today=TODAY) == (
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
def test_fetch_football_results_sends_key_as_header_not_query_param() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, json={"matches": []}, status=200)

    fetch_football_results(today=TODAY)

    request = responses.calls[0].request
    assert request.headers["X-Auth-Token"] == API_KEY
    assert API_KEY not in str(request.url)


@responses.activate
def test_fetch_football_results_requests_the_lookback_window() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, json={"matches": []}, status=200)

    fetch_football_results(today=TODAY, lookback_days=2)

    url = str(responses.calls[0].request.url)
    assert "dateFrom=2026-08-15" in url
    assert "dateTo=2026-08-17" in url
    assert "competitions=PL%2CPD%2CSA" in url


@responses.activate
def test_fetch_football_results_skips_matches_that_are_not_finished() -> None:
    responses.add(
        responses.GET,
        FOOTBALL_MATCHES_URL,
        json={"matches": [_match(status="SCHEDULED"), _match(status="POSTPONED"), _match()]},
        status=200,
    )

    assert len(fetch_football_results(today=TODAY)) == 1


@responses.activate
@pytest.mark.parametrize(
    "broken",
    [
        {"score": {"fullTime": {"home": None, "away": None}}},
        {"score": {"fullTime": {}}},
        {"score": {}},
        {"homeTeam": {}},
        {"awayTeam": {"name": ""}},
        {"utcDate": "not-a-date"},
        {"utcDate": None},
    ],
)
def test_fetch_football_results_skips_unusable_matches(broken: dict[str, Any]) -> None:
    responses.add(
        responses.GET,
        FOOTBALL_MATCHES_URL,
        json={"matches": [_match(**broken), "not-an-object", _match()]},
        status=200,
    )

    matches = fetch_football_results(today=TODAY)

    assert [match.home_team for match in matches] == ["Arsenal FC"]


@responses.activate
def test_fetch_football_results_returns_empty_on_http_error() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, json={"message": "rate limit"}, status=429)

    assert fetch_football_results(today=TODAY) == ()


@responses.activate
def test_fetch_football_results_returns_empty_on_connection_error() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, body=requests.ConnectionError("down"))

    assert fetch_football_results(today=TODAY) == ()


@responses.activate
def test_fetch_football_results_returns_empty_on_invalid_json() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, body="<html>oops</html>", status=200)

    assert fetch_football_results(today=TODAY) == ()


@responses.activate
def test_fetch_football_results_returns_empty_on_payload_without_matches() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, json={"errorCode": 400}, status=200)

    assert fetch_football_results(today=TODAY) == ()


def test_fetch_football_results_returns_empty_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOOTBALL_DATA_API_KEY", raising=False)

    assert fetch_football_results(today=TODAY) == ()


@responses.activate
def test_fetch_football_results_warning_does_not_leak_the_api_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 403 puts the request URL into the exception; the key must not follow."""
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, json={"message": "forbidden"}, status=403)

    with caplog.at_level(logging.WARNING):
        assert fetch_football_results(today=TODAY) == ()

    assert caplog.records, "expected a warning to be logged"
    assert API_KEY not in caplog.text


# --- formula 1 --------------------------------------------------------------


@responses.activate
def test_fetch_f1_result_returns_the_podium_in_finishing_order() -> None:
    responses.add(responses.GET, F1_LAST_RACE_URL, json=_f1_payload(_race()), status=200)

    assert fetch_f1_result(today=TODAY) == RaceResult(
        name="Hungarian Grand Prix",
        race_date=date(2026, 8, 16),
        podium=(
            DriverResult(position=1, driver="Lando Norris", constructor="McLaren"),
            DriverResult(position=2, driver="Oscar Piastri", constructor="McLaren"),
            DriverResult(position=3, driver="Max Verstappen", constructor="Red Bull"),
        ),
    )


@responses.activate
def test_fetch_f1_result_returns_none_for_a_stale_race() -> None:
    """The endpoint always returns the last race, however long ago it was."""
    responses.add(
        responses.GET, F1_LAST_RACE_URL, json=_f1_payload(_race(date="2026-07-26")), status=200
    )

    assert fetch_f1_result(today=TODAY) is None


@responses.activate
def test_fetch_f1_result_includes_a_race_at_the_edge_of_the_window() -> None:
    responses.add(
        responses.GET, F1_LAST_RACE_URL, json=_f1_payload(_race(date="2026-08-14")), status=200
    )

    race = fetch_f1_result(today=TODAY, lookback_days=3)

    assert race is not None
    assert race.race_date == date(2026, 8, 14)


@responses.activate
def test_fetch_f1_result_skips_drivers_without_a_usable_position() -> None:
    responses.add(
        responses.GET,
        F1_LAST_RACE_URL,
        json=_f1_payload(
            _race(
                Results=[
                    {"position": "NC", "Driver": {"familyName": "Ocon"}},
                    "not-an-object",
                    {"position": "1", "Driver": {}},
                    {"position": "2", "Driver": {"familyName": "Alonso"}},
                ]
            )
        ),
        status=200,
    )

    race = fetch_f1_result(today=TODAY)

    assert race is not None
    assert race.podium == (DriverResult(position=2, driver="Alonso", constructor=""),)


@responses.activate
@pytest.mark.parametrize(
    "payload",
    [
        {"MRData": {"RaceTable": {"Races": []}}},
        {"MRData": {"RaceTable": {}}},
        {"MRData": {}},
        {"unexpected": "shape"},
        [],
    ],
)
def test_fetch_f1_result_returns_none_when_no_race_is_present(payload: Any) -> None:
    responses.add(responses.GET, F1_LAST_RACE_URL, json=payload, status=200)

    assert fetch_f1_result(today=TODAY) is None


@responses.activate
@pytest.mark.parametrize(
    "broken",
    [{"raceName": ""}, {"date": "not-a-date"}, {"Results": []}, {"Results": "nope"}],
)
def test_fetch_f1_result_returns_none_for_an_unparsable_race(broken: dict[str, Any]) -> None:
    responses.add(responses.GET, F1_LAST_RACE_URL, json=_f1_payload(_race(**broken)), status=200)

    assert fetch_f1_result(today=TODAY) is None


@responses.activate
def test_fetch_f1_result_returns_none_when_the_race_is_not_an_object() -> None:
    responses.add(
        responses.GET,
        F1_LAST_RACE_URL,
        json={"MRData": {"RaceTable": {"Races": ["not-an-object"]}}},
        status=200,
    )

    assert fetch_f1_result(today=TODAY) is None


@responses.activate
def test_fetch_f1_result_returns_none_on_http_error() -> None:
    responses.add(responses.GET, F1_LAST_RACE_URL, json={"error": "nope"}, status=503)

    assert fetch_f1_result(today=TODAY) is None


@responses.activate
def test_fetch_f1_result_returns_none_on_connection_error() -> None:
    responses.add(responses.GET, F1_LAST_RACE_URL, body=requests.ConnectionError("down"))

    assert fetch_f1_result(today=TODAY) is None


# --- combined ---------------------------------------------------------------


@responses.activate
def test_fetch_sports_combines_both_sources() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, json={"matches": [_match()]}, status=200)
    responses.add(responses.GET, F1_LAST_RACE_URL, json=_f1_payload(_race()), status=200)

    report = fetch_sports(today=TODAY)

    assert len(report.matches) == 1
    assert report.race is not None
    assert report.has_results


@responses.activate
def test_fetch_sports_survives_one_dead_source() -> None:
    """A broken football fetch must not cost the category its F1 half."""
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, body=requests.ConnectionError("down"))
    responses.add(responses.GET, F1_LAST_RACE_URL, json=_f1_payload(_race()), status=200)

    report = fetch_sports(today=TODAY)

    assert report.matches == ()
    assert report.race is not None
    assert report.has_results


@responses.activate
def test_fetch_sports_reports_no_results_in_the_off_season() -> None:
    responses.add(responses.GET, FOOTBALL_MATCHES_URL, json={"matches": []}, status=200)
    responses.add(
        responses.GET, F1_LAST_RACE_URL, json=_f1_payload(_race(date="2026-06-01")), status=200
    )

    report = fetch_sports(today=TODAY)

    assert report == SportsReport(matches=(), race=None)
    assert not report.has_results
