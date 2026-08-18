"""Fetch recent football results for PLAN.md category 4.

The category has shrunk to a single source, football-data.org, covering the
Premier League, La Liga and Serie A. The three sources named in ``PLAN.md`` all
fell through — API-Football's free plan refuses the current season, Ergast
answers 403, and balldontlie started requiring a key — and the two categories
that survived on replacement sources have since been dropped by choice: NBA
first, then Formula 1. The Turkish Süper Lig is not on football-data.org's free
tier, so it is not covered either.

Results are filtered to a recency window so that a Monday run still picks up
the weekend fixtures without re-reporting them all week.
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

# football-data.org competition codes available on the free tier.
COMPETITIONS: tuple[str, ...] = ("PL", "PD", "SA")

DEFAULT_LOOKBACK_DAYS = 2
REQUEST_TIMEOUT_SECONDS = 10

# What the summarizer should say when there were no fixtures.
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


def _text(raw: Any, key: str) -> str:
    """Read a string field from a payload object, defaulting to an empty string."""
    if not isinstance(raw, dict):
        return ""
    value = raw.get(key)
    return value.strip() if isinstance(value, str) else ""


def _parse_utc_date(raw_timestamp: Any) -> date | None:
    """Convert an ISO-8601 UTC timestamp such as ``2026-08-15T14:00:00Z`` to a date."""
    if not isinstance(raw_timestamp, str):
        return None
    try:
        return datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00")).date()
    except ValueError:
        return None


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


def fetch_sports(
    today: date | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> tuple[MatchResult, ...]:
    """Fetch finished league matches from the last ``lookback_days`` days.

    Never raises. A missing API key, a network failure, an HTTP error or a
    malformed response all produce an empty tuple plus a logged warning, so the
    sports category degrades to "nothing notable" without affecting the other
    three categories. An empty result is also the normal off-season outcome.

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
