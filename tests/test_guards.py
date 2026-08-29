"""Tests for the autouse guards in conftest.py.

The guards only ever act by *absence* — nothing fails when they work — so they
are worth asserting directly: a guard that silently stopped applying would look
exactly like a guard that was never needed.
"""

import os

import pytest
import requests

from app.config import MissingEnvVarError, load_anthropic_settings
from tests.conftest import GUARDED_ENV_VARS, config_required_env_vars


def test_the_guard_covers_every_secret_config_requires() -> None:
    """A secret added to config.py without being listed here would leak the real value."""
    assert config_required_env_vars() <= set(GUARDED_ENV_VARS)


def test_real_credentials_are_not_visible_to_a_test_that_forgets_to_set_one() -> None:
    assert not [name for name in GUARDED_ENV_VARS if os.environ.get(name)]

    with pytest.raises(MissingEnvVarError):
        load_anthropic_settings()


def test_an_unmocked_http_call_is_blocked() -> None:
    with pytest.raises(requests.ConnectionError):
        requests.get("https://example.invalid", timeout=1)
