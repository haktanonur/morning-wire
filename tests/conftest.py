"""Global test guards: no real credentials, no real network.

Every test module that touches a secret sets its own fake value, but that is a
convention rather than a rule, and a test that forgets falls through to the
developer's real ``.env`` — which ``app.config`` loads at import time. The
failure mode is quiet and expensive: the test passes locally against live
credentials, spends real API quota or fires a real SMS, then fails in CI where
no ``.env`` exists.

Both fixtures below are autouse, so forgetting is no longer possible.
"""

from __future__ import annotations

import ast
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

# Every secret app.config reads. Cleared before each test so a module that does
# not set its own value gets a MissingEnvVarError rather than the real key.
# test_config.py asserts this list still matches config.py.
GUARDED_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "FINNHUB_API_KEY",
    "FOOTBALL_DATA_API_KEY",
    "MACRODROID_TRIGGER_URL",
)


@pytest.fixture(autouse=True)
def _no_real_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hide the developer's real credentials from every test."""
    for name in GUARDED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Fail loudly if a test opens a real connection.

    ``responses`` and ``pytest-mock`` intercept above the socket layer, so a
    mocked test never reaches this. An unmocked one currently makes a real call
    to Finnhub or Anthropic and merely runs slowly; here it raises instead.
    """

    def _blocked(*args: object, **kwargs: object) -> None:
        raise RuntimeError(
            "A test tried to open a network connection. Mock the HTTP call "
            "(responses / pytest-mock) rather than letting it out."
        )

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    yield


def config_required_env_vars() -> frozenset[str]:
    """The names app.config passes to ``get_required_env``, read from its source.

    Parsed rather than imported so the answer comes from the code itself: a new
    secret added to config.py shows up here without anyone remembering to
    update a list.
    """
    source = Path(__file__).resolve().parents[1] / "src" / "app" / "config.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    return frozenset(
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "get_required_env"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    )
