"""Fetch recent sports results for PLAN.md category 4.

Two sources are polled independently so a failure costs only its own half of the
category:

* football-data.org for the European leagues (Premier League, La Liga, Serie A)
* Jolpica, an Ergast-compatible mirror, for Formula 1

Neither source named in ``PLAN.md`` survived contact with reality: the original
Ergast API now answers 403, and API-Football's free plan refuses the current
season. The Turkish Süper Lig is not part of football-data.org's free tier, so
it is not covered here.

Both sources are filtered to a recency window. Without it the F1 endpoint would
repeat the same weeks-old race every morning, since it always returns the last
race that happened regardless of how long ago that was.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import requests

from app.config import load_football_data_settings

logger = logging.getLogger(__name__)

FOOTBALL_MATCHES_URL = "https://api.football-data.org/v4/matches"
F1_LAST_RACE_URL = "https://api.jolpi.ca/ergast/f1/current/last/results.json"

# football-data.org competition codes available on the free tier.
COMPETITIONS: tuple[str, ...] = ("PL", "PD", "SA")

DEFAULT_FOOTBALL_LOOKBACK_DAYS = 2
DEFAULT_F1_LOOKBACK_DAYS = 3
PODIUM_SIZE = 3
REQUEST_TIMEOUT_SECONDS = 10

# What the summarizer should say when neither source had anything to report.
NOTHING_NOTABLE = "nothing notable today"


@dataclass(frozen=True)
class MatchResult:
    """A single finished football match.

    Attributes:
        competition: League name, e.g. ``"Premier League"``.
        home_team: Home side's name.
        away_team: Away side's name.
        home_score: Full-time goals for the home side.
        away_score: Full-time goals for the away side.
        played_on: Kick-off date in UTC.
    """

    competition: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    played_on: date


@dataclass(frozen=True)
class DriverResult:
    """One driver's finishing position in a race."""

    position: int
    driver: str
    constructor: str


@dataclass(frozen=True)
class RaceResult:
    """A Formula 1 race and its podium.

    Attributes:
        name: Official race name, e.g. ``"Hungarian Grand Prix"``.
        race_date: Date the race was held.
        podium: Up to the top three finishers, in finishing order.
    """

    name: str
    race_date: date
    podium: tuple[DriverResult, ...]


@dataclass(frozen=True)
class SportsReport:
    """Everything the sports category has for one run.

    Either half may be empty; ``has_results`` tells the caller whether the
    category has anything worth printing at all.
    """

    matches: tuple[MatchResult, ...]
    race: RaceResult | None

    @property
    def has_results(self) -> bool:
        """Whether any source returned something. False means ``NOTHING_NOTABLE``."""
        return bool(self.matches) or self.race is not None


def _text(raw: Any, key: str) -> str:
    """Read a string field from a payload object, defaulting to an empty string."""
    if not isinstance(raw, dict):
        return ""
    value = raw.get(key)
    return value.strip() if isinstance(value, str) else ""


def _parse_match(raw: Any) -> MatchResult | None:
    """Build a MatchResult from one football-data.org match, or None if unusable.

    Only finished matches carry a result worth summarizing; anything scheduled,
    postponed or in progress is dropped rather than surfaced with a blank score.
    """
    if not isinstance(raw, dict) or raw.get("status") != "FINISHED":
        return None

    home_team = _text(raw.get("homeTeam"), "name")
    away_team = _text(raw.get("awayTeam"), "name")
    if not home_team or not away_team:
        return None

    score = raw.get("score")
    full_time = score.get("fullTime") if isinstance(score, dict) else None
    if not isinstance(full_time, dict):
        return None
    home_score = full_time.get("home")
    away_score = full_time.get("away")
    if not isinstance(home_score, int) or not isinstance(away_score, int):
        return None

    played_on = _parse_utc_date(raw.get("utcDate"))
    if played_on is None:
        return None

    return MatchResult(
        competition=_text(raw.get("competition"), "name"),
        home_team=home_team,
        away_team=away_team,
        home_score=home_score,
        away_score=away_score,
        played_on=played_on,
    )


def _parse_utc_date(raw_timestamp: Any) -> date | None:
    """Convert an ISO-8601 UTC timestamp such as ``2026-08-15T14:00:00Z`` to a date."""
    if not isinstance(raw_timestamp, str):
        return None
    try:
        return datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _parse_driver(raw: Any) -> DriverResult | None:
    """Build a DriverResult from one Ergast result entry, or None if unusable."""
    if not isinstance(raw, dict):
        return None
    try:
        position = int(raw["position"])
    except (KeyError, TypeError, ValueError):
        return None

    driver = raw.get("Driver")
    parts = (_text(driver, "givenName"), _text(driver, "familyName"))
    name = " ".join(part for part in parts if part)
    if not name:
        return None

    return DriverResult(
        position=position,
        driver=name,
        constructor=_text(raw.get("Constructor"), "name"),
    )


def _parse_race(raw: Any) -> RaceResult | None:
    """Build a RaceResult from one Ergast race, or None if it has no usable podium."""
    if not isinstance(raw, dict):
        return None

    name = _text(raw, "raceName")
    if not name:
        return None

    try:
        race_date = date.fromisoformat(raw.get("date", ""))
    except (TypeError, ValueError):
        return None

    results = raw.get("Results")
    if not isinstance(results, list):
        return None
    drivers = [driver for entry in results if (driver := _parse_driver(entry)) is not None]
    if not drivers:
        return None

    drivers.sort(key=lambda driver: driver.position)
    return RaceResult(name=name, race_date=race_date, podium=tuple(drivers[:PODIUM_SIZE]))


def fetch_football_results(
    today: date | None = None,
    lookback_days: int = DEFAULT_FOOTBALL_LOOKBACK_DAYS,
) -> tuple[MatchResult, ...]:
    """Fetch finished league matches from the last ``lookback_days`` days.

    Never raises. A missing API key, a network failure, an HTTP error or a
    malformed response all produce an empty tuple plus a logged warning, so the
    F1 half of the category still gets through.

    Args:
        today: The day the report is being generated for. Defaults to the
            current UTC date; injectable so tests are deterministic.
        lookback_days: How many days back to include, so a run on Monday still
            picks up the weekend fixtures.

    Returns:
        Finished matches in the window, in the order football-data.org returns them.
    """
    today = today or datetime.now(UTC).date()
    date_from = date.fromordinal(today.toordinal() - max(lookback_days, 0))

    try:
        settings = load_football_data_settings()
        response = requests.get(
            FOOTBALL_MATCHES_URL,
            params={
                "competitions": ",".join(COMPETITIONS),
                "dateFrom": date_from.isoformat(),
                "dateTo": today.isoformat(),
            },
            # Header auth rather than a query param: request URLs end up in
            # exception messages and logs, and the key must never leak there.
            headers={"X-Auth-Token": settings.api_key},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.warning(
            "Football results fetch failed (%s); returning no matches.", type(exc).__name__
        )
        return ()

    raw_matches = payload.get("matches") if isinstance(payload, dict) else None
    if not isinstance(raw_matches, list):
        logger.warning("Football results response had no match list; returning no matches.")
        return ()

    return tuple(match for raw in raw_matches if (match := _parse_match(raw)) is not None)


def fetch_f1_result(
    today: date | None = None,
    lookback_days: int = DEFAULT_F1_LOOKBACK_DAYS,
) -> RaceResult | None:
    """Fetch the most recent F1 race, if it happened within ``lookback_days``.

    Never raises. The endpoint always returns the last race that took place, so
    the recency check is what stops a race from mid-season being re-reported
    every morning through a three-week summer break.

    Args:
        today: The day the report is being generated for. Defaults to the
            current UTC date; injectable so tests are deterministic.
        lookback_days: How recent the race must be to count as news.

    Returns:
        The race and its podium, or ``None`` if there was no recent race or the
        fetch failed.
    """
    today = today or datetime.now(UTC).date()

    try:
        response = requests.get(F1_LAST_RACE_URL, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.warning("F1 results fetch failed (%s); returning no race.", type(exc).__name__)
        return None

    races = None
    if isinstance(payload, dict):
        race_table = payload.get("MRData", {}).get("RaceTable", {})
        if isinstance(race_table, dict):
            races = race_table.get("Races")
    if not isinstance(races, list) or not races:
        logger.warning("F1 results response contained no races; returning no race.")
        return None

    race = _parse_race(races[0])
    if race is None:
        logger.warning("F1 race could not be parsed; returning no race.")
        return None

    if (today - race.race_date).days > max(lookback_days, 0):
        return None
    return race


def fetch_sports(today: date | None = None) -> SportsReport:
    """Fetch both halves of the sports category.

    Never raises. An empty report is a legitimate outcome (off-season, no
    fixtures) and the caller should render it as ``NOTHING_NOTABLE``.

    Args:
        today: The day the report is being generated for. Defaults to the
            current UTC date; injectable so tests are deterministic.
    """
    today = today or datetime.now(UTC).date()
    report = SportsReport(
        matches=fetch_football_results(today=today),
        race=fetch_f1_result(today=today),
    )
    if not report.has_results:
        logger.info("Sports sources returned nothing for %s.", today.isoformat())
    return report
