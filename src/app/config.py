"""Single entry point for reading settings from environment variables.

No other module should read os.environ directly; everything goes through
the helpers here so secrets usage stays traceable in one place and is easy
to mock in tests.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class MissingEnvVarError(RuntimeError):
    """Raised when a required environment variable is not set."""


def get_required_env(name: str) -> str:
    """Read a required environment variable, raising a clear error if missing."""
    value = os.environ.get(name)
    if not value:
        raise MissingEnvVarError(
            f"Missing required environment variable: {name}. See .env.example."
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
class TwilioSettings:
    account_sid: str
    auth_token: str
    from_number: str
    to_number: str


def load_twilio_settings() -> TwilioSettings:
    """Load Twilio settings from the environment. Used by sender.py (Phase 2, not yet built)."""
    return TwilioSettings(
        account_sid=get_required_env("TWILIO_ACCOUNT_SID"),
        auth_token=get_required_env("TWILIO_AUTH_TOKEN"),
        from_number=get_required_env("TWILIO_FROM_NUMBER"),
        to_number=get_required_env("TWILIO_TO_NUMBER"),
    )
