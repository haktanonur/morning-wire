import logging
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import responses

from app.config import MissingEnvVarError
from app.sender import (
    MESSAGE_PARAM,
    SendOutcome,
    build_message,
    build_url,
    send_report,
)
from app.sms_text import GSM7_BASIC, GSM7_EXTENSION

TRIGGER_URL = "https://trigger.macrodroid.com/fake-device-id/daily-sms-bot"

SECTIONS = (
    ("MARKETS", "Piyasalar yatay seyretti."),
    ("PORTFOLIO", "Portföy hafif artıda."),
    ("NEWS", "Meclis bütçeyi görüştü."),
    ("SPORTS", "Arsenal 2-1 kazandı."),
)


@pytest.fixture(autouse=True)
def _trigger_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test a known trigger URL so nothing falls through to the real .env."""
    monkeypatch.setenv("MACRODROID_TRIGGER_URL", TRIGGER_URL)


def _ok(status: int = 200, body: str = "ok") -> None:
    responses.add(responses.GET, TRIGGER_URL, body=body, status=status)


def _sent_messages() -> list[str]:
    queries = (urlparse(call.request.url).query for call in responses.calls)
    return [parse_qs(query)[MESSAGE_PARAM][0] for query in queries]


# --- message body -----------------------------------------------------------


def test_build_message_prefixes_the_category_tag() -> None:
    assert build_message("MARKETS", "Piyasalar yatay.").startswith("[MARKETS] ")


def test_build_message_folds_turkish_into_gsm7() -> None:
    body = build_message("PORTFOLIO", "Portföy günü artıda kapattı — şirket hissesi yükseldi.")

    assert "Portfoy gunu artida kapatti - sirket hissesi yukseldi." in body
    assert all(char in GSM7_BASIC or char in GSM7_EXTENSION for char in body)


def test_build_message_keeps_the_unavailable_marker_readable() -> None:
    """main.py renders a failed category as '[unavailable: ...]'; the brackets must survive."""
    body = build_message("SPORTS", "[unavailable: HTTPError]")

    assert body == "[SPORTS] [unavailable: HTTPError]"


# --- URL construction -------------------------------------------------------


def test_build_url_encodes_a_space_as_percent_twenty() -> None:
    """MacroDroid documents %20 and says nothing about '+', so requests' params= is not used."""
    url = build_url(TRIGGER_URL, "[MARKETS] Piyasalar yatay")

    assert "+" not in url
    assert "%20" in url


@pytest.mark.parametrize("char", ["&", "=", "#", "?", "+", "%", "\n"])
def test_build_url_escapes_reserved_characters(char: str) -> None:
    """A raw '&' in the body would truncate the message and invent a second parameter."""
    url = build_url(TRIGGER_URL, f"before{char}after")

    assert parse_qs(urlparse(url).query)[MESSAGE_PARAM] == [f"before{char}after"]


def test_build_url_keeps_the_trigger_url_intact() -> None:
    assert build_url(TRIGGER_URL, "hi").startswith(f"{TRIGGER_URL}?{MESSAGE_PARAM}=")


# --- sending ----------------------------------------------------------------


@responses.activate
def test_send_report_fires_one_request_per_category_in_order() -> None:
    for _ in SECTIONS:
        _ok()

    outcomes = send_report(SECTIONS)

    assert len(responses.calls) == len(SECTIONS)
    assert [outcome.heading for outcome in outcomes] == ["MARKETS", "PORTFOLIO", "NEWS", "SPORTS"]
    assert [message.split("]")[0] for message in _sent_messages()] == [
        "[MARKETS",
        "[PORTFOLIO",
        "[NEWS",
        "[SPORTS",
    ]


@responses.activate
def test_send_report_sends_the_folded_body() -> None:
    _ok()

    send_report([SECTIONS[1]])

    assert _sent_messages() == ["[PORTFOLIO] Portfoy hafif artida."]


@responses.activate
def test_send_report_reports_success_when_the_relay_accepts() -> None:
    _ok()

    (outcome,) = send_report([SECTIONS[0]])

    assert outcome == SendOutcome(heading="MARKETS")
    assert outcome.accepted


@responses.activate
def test_send_report_sends_nothing_for_an_empty_report() -> None:
    assert send_report([]) == ()
    assert not responses.calls


# --- per-category error isolation -------------------------------------------


@responses.activate
def test_send_report_continues_after_one_category_fails() -> None:
    """AGENTS.md rule 4: one dead category must not cost the other three."""
    _ok()
    _ok(status=500)
    _ok()
    _ok()

    outcomes = send_report(SECTIONS)

    assert len(responses.calls) == len(SECTIONS)
    assert [outcome.accepted for outcome in outcomes] == [True, False, True, True]


@responses.activate
def test_send_report_treats_an_unknown_trigger_as_a_failure() -> None:
    """A typo in the trigger name answers 404, not 200."""
    _ok(status=404, body='{"error":"Not found"}')

    (outcome,) = send_report([SECTIONS[0]])

    assert outcome.error == "HTTPError"


@responses.activate
def test_send_report_treats_rate_limiting_as_a_failure() -> None:
    _ok(status=429)

    (outcome,) = send_report([SECTIONS[0]])

    assert not outcome.accepted


@responses.activate
def test_send_report_survives_a_network_failure() -> None:
    responses.add(responses.GET, TRIGGER_URL, body=requests.ConnectionError("no route"))

    (outcome,) = send_report([SECTIONS[0]])

    assert outcome.error == "ConnectionError"


@responses.activate
def test_send_report_error_does_not_quote_the_trigger_url() -> None:
    """requests puts the failing URL in its message, and that URL is the credential."""
    _ok(status=500)

    (outcome,) = send_report([SECTIONS[0]])

    assert outcome.error is not None
    assert "macrodroid.com" not in outcome.error


@responses.activate
def test_send_report_does_not_log_the_trigger_url(caplog: pytest.LogCaptureFixture) -> None:
    _ok(status=500)

    with caplog.at_level(logging.WARNING):
        send_report([SECTIONS[0]])

    assert "MARKETS" in caplog.text
    assert "macrodroid.com" not in caplog.text


# --- weaker signals ---------------------------------------------------------


@responses.activate
def test_send_report_warns_but_accepts_an_unexpected_body(caplog: pytest.LogCaptureFixture) -> None:
    """The status is the contract; a surprising body is worth surfacing, not failing."""
    _ok(body="something else")

    with caplog.at_level(logging.WARNING):
        (outcome,) = send_report([SECTIONS[0]])

    assert outcome.accepted
    assert "unexpected body" in caplog.text


@responses.activate
def test_send_report_does_not_warn_on_the_expected_body(caplog: pytest.LogCaptureFixture) -> None:
    _ok(body="OK\n")

    with caplog.at_level(logging.WARNING):
        send_report([SECTIONS[0]])

    assert not caplog.records


# --- configuration ----------------------------------------------------------


@responses.activate
def test_send_report_raises_when_the_trigger_url_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing URL breaks every category, so this one is not swallowed."""
    monkeypatch.delenv("MACRODROID_TRIGGER_URL", raising=False)

    with pytest.raises(MissingEnvVarError):
        send_report(SECTIONS)

    assert not responses.calls
