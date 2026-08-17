import pytest

from app.config import (
    MissingEnvVarError,
    get_required_env,
    load_anthropic_settings,
    load_twilio_settings,
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


def test_load_twilio_settings_reads_all_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "sid")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+1000")
    monkeypatch.setenv("TWILIO_TO_NUMBER", "+2000")

    settings = load_twilio_settings()

    assert settings.account_sid == "sid"
    assert settings.auth_token == "token"
    assert settings.from_number == "+1000"
    assert settings.to_number == "+2000"
