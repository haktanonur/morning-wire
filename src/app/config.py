"""Single entry point for reading settings from environment variables.

No other module should read os.environ directly; everything goes through
the helpers here so secrets usage stays traceable in one place and is easy
to mock in tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load the developer's .env on import so every caller sees the same environment.
# Explicit path rather than a CWD-relative search, so `python -m app.main` behaves
# the same regardless of the directory it was launched from. Existing environment
# variables win over the file, which is what lets the GitHub Actions run (Phase 3)
# supply these from repository secrets with no .env present at all.
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_FILE, override=False)


class MissingEnvVarError(RuntimeError):
    """Raised when a required environment variable is not set."""


def get_required_env(name: str) -> str:
    """Read a required environment variable, raising a clear error if missing."""
    value = os.environ.get(name)
    if not value:
        raise MissingEnvVarError(
            f"Missing required environment variable: {name}. See the table in README.md."
        )
    return value


def get_optional_env(name: str, default: str = "") -> str:
    """Read an optional environment variable, falling back to a default."""
    return os.environ.get(name, default)


@dataclass(frozen=True)
class AnthropicSettings:
    api_key: str


def load_anthropic_settings() -> AnthropicSettings:
    """Load Claude API settings from the environment. Used by summarizer.py (Phase 1)."""
    return AnthropicSettings(api_key=get_required_env("ANTHROPIC_API_KEY"))


@dataclass(frozen=True)
class FinnhubSettings:
    api_key: str


def load_finnhub_settings() -> FinnhubSettings:
    """Load Finnhub settings from the environment. Used by fetchers/market_news.py (Phase 1)."""
    return FinnhubSettings(api_key=get_required_env("FINNHUB_API_KEY"))


@dataclass(frozen=True)
class FootballDataSettings:
    api_key: str


def load_football_data_settings() -> FootballDataSettings:
    """Load football-data.org settings. Used by fetchers/sports.py (Phase 1)."""
    return FootballDataSettings(api_key=get_required_env("FOOTBALL_DATA_API_KEY"))


@dataclass(frozen=True)
class MacroDroidSettings:
    trigger_url: str


def load_macrodroid_settings() -> MacroDroidSettings:
    """Load the MacroDroid webhook settings. Used by sender.py (Phase 2).

    The trigger URL is itself the credential — it embeds the device id, and
    anyone holding it can fire the macro — so it is read from the environment
    like any other secret rather than written into the code.
    """
    return MacroDroidSettings(trigger_url=get_required_env("MACRODROID_TRIGGER_URL"))
