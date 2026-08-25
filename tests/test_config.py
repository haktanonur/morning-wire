import pytest

from app.config import (
    MissingEnvVarError,
    get_required_env,
    load_anthropic_settings,
    load_finnhub_settings,
    load_football_data_settings,
    load_macrodroid_settings,
)


def test_get_required_env_returns_value_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOME_VAR", "hello")
    assert get_required_env("SOME_VAR") == "hello"


def test_get_required_env_raises_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOME_VAR", raising=False)
    with pytest.raises(MissingEnvVarError):
        get_required_env("SOME_VAR")


def test_load_anthropic_settings_reads_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
    settings = load_anthropic_settings()
    assert settings.api_key == "sk-test-123"


def test_load_finnhub_settings_reads_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "finnhub-test-123")
    assert load_finnhub_settings().api_key == "finnhub-test-123"


def test_load_finnhub_settings_raises_when_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    with pytest.raises(MissingEnvVarError):
        load_finnhub_settings()


def test_load_football_data_settings_reads_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", "football-data-test-123")
    assert load_football_data_settings().api_key == "football-data-test-123"


def test_load_football_data_settings_raises_when_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FOOTBALL_DATA_API_KEY", raising=False)
    with pytest.raises(MissingEnvVarError):
        load_football_data_settings()


def test_load_macrodroid_settings_reads_the_trigger_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MACRODROID_TRIGGER_URL", "https://trigger.macrodroid.com/id/name")
    assert load_macrodroid_settings().trigger_url == "https://trigger.macrodroid.com/id/name"


def test_load_macrodroid_settings_raises_when_the_url_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MACRODROID_TRIGGER_URL", raising=False)
    with pytest.raises(MissingEnvVarError):
        load_macrodroid_settings()
