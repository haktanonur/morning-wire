"""End-to-end test of the whole pipeline, stubbed only at its outer edges.

Every other test file mocks its neighbours: ``test_main.py`` patches the
fetchers and the summarizer, ``test_summarizer.py`` patches the Anthropic
client, ``test_sender.py`` patches HTTP. Each is honest on its own, and together
they leave a gap — nothing checks that the pieces still fit. The
``Section``-to-tuple conversion between ``main.py`` and ``sender.py``, the
category tag, the GSM-7 fold and the send order are all seams that no unit test
crosses.

So this file stubs only what leaves the machine — yfinance, Finnhub's HTTP,
feedparser, football-data's HTTP, the Anthropic client and the MacroDroid
webhook — and lets everything in between run for real. The strongest assertion
here is that a headline injected into the Finnhub response comes back out in the
body of the ``[MARKETS]`` SMS, folded and tagged: that one line covers the
entire chain for a category.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest
import responses
from pytest_mock import MockerFixture

from app.fetchers.market_news import FINNHUB_NEWS_URL
from app.fetchers.sports import FOOTBALL_MATCHES_URL
from app.main import main
from app.sender import MESSAGE_PARAM

TRIGGER_URL = "https://trigger.macrodroid.com/fake-device-id/daily-sms-bot"

# One ASCII word planted in each category's source data. The stubbed model
# echoes back whichever one it was given, which is what lets a single assertion
# prove that this category's data travelled through this category's prompt and
# came out in this category's SMS. They are kept free of Turkish letters so the
# expected strings below stay readable after the fold.
MARKERS = ("Fed", "TSLA", "Meclis", "Arsenal")


def _reply(text: str) -> SimpleNamespace:
    """The shape of an Anthropic response, as summarizer._extract_text reads it."""
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def _summarize_by_echoing_the_marker(**kwargs: Any) -> SimpleNamespace:
    """Stand in for Claude: answer in Turkish, naming whichever marker it was sent.

    The diacritics are the point as much as the marker is — they are what
    ``sms_text.to_gsm7`` has to fold before the message can fit 153-character
    segments instead of 67.
    """
    content = kwargs["messages"][0]["content"]
    marker = next((marker for marker in MARKERS if marker in content), "hiçbir şey")
    return _reply(f"Bugün {marker} öne çıktı.")


@pytest.fixture
def world(mocker: MockerFixture, tmp_path: Path) -> Iterator[responses.RequestsMock]:
    """Stub every edge of the system and nothing inside it.

    Yields the HTTP mock so a test can override a registered response — that is
    how the "one dead source" case is set up.
    """
    for name in ("ANTHROPIC_API_KEY", "FINNHUB_API_KEY", "FOOTBALL_DATA_API_KEY"):
        mocker.patch.dict("os.environ", {name: f"fake-{name.lower()}"})
    mocker.patch.dict("os.environ", {"MACRODROID_TRIGGER_URL": TRIGGER_URL})

    # Real file, real JSON parsing, just not the owner's real holdings.
    config_path = tmp_path / "portfolio.json"
    config_path.write_text(
        json.dumps({"symbols": [{"ticker": "TSLA", "label": "Tesla"}]}), encoding="utf-8"
    )
    mocker.patch("app.fetchers.portfolio.DEFAULT_PORTFOLIO_PATH", config_path)

    handle = mocker.Mock()
    handle.history.return_value = pd.DataFrame({"Close": [400.0, 412.0]})
    mocker.patch("app.fetchers.portfolio.yf.Ticker", return_value=handle)

    mocker.patch(
        "app.fetchers.general_news.feedparser.parse",
        return_value=SimpleNamespace(
            status=200,
            entries=[{"title": "Meclis toplandi", "link": "https://example.com/1", "summary": ""}],
        ),
    )

    client = SimpleNamespace(
        messages=SimpleNamespace(create=mocker.Mock(side_effect=_summarize_by_echoing_the_marker))
    )
    mocker.patch("app.summarizer.anthropic.Anthropic", return_value=client)

    # assert_all_requests_are_fired is off because --dry-run deliberately never
    # calls the relay, and that is a case worth testing.
    with responses.RequestsMock(assert_all_requests_are_fired=False) as http:
        http.add(
            responses.GET,
            FINNHUB_NEWS_URL,
            json=[{"headline": "Fed held rates steady", "source": "Reuters", "url": "", "id": 1}],
        )
        http.add(
            responses.GET,
            FOOTBALL_MATCHES_URL,
            json={
                "matches": [
                    {
                        "status": "FINISHED",
                        "utcDate": "2026-08-29T14:00:00Z",
                        "competition": {"name": "Premier League"},
                        "homeTeam": {"name": "Arsenal"},
                        "awayTeam": {"name": "Chelsea"},
                        "score": {"fullTime": {"home": 2, "away": 1}},
                    }
                ]
            },
        )
        http.add(responses.GET, TRIGGER_URL, body="ok")
        yield http


def _sent_messages(http: responses.RequestsMock) -> list[str]:
    """The message bodies that actually reached the relay, in send order."""
    triggers = (call for call in http.calls if TRIGGER_URL in call.request.url)
    queries = (urlparse(call.request.url).query for call in triggers)
    return [parse_qs(query)[MESSAGE_PARAM][0] for query in queries]


def test_the_whole_pipeline_delivers_four_tagged_folded_messages(
    world: responses.RequestsMock,
) -> None:
    """Source data in, SMS out, with nothing between the two mocked.

    The expected strings are spelled out rather than computed: "Bugün ... öne
    çıktı." folded to ASCII is exactly this, and writing it by hand is what
    makes a regression in the fold visible instead of self-consistent.
    """
    assert main([]) == 0

    assert _sent_messages(world) == [
        "[MARKETS] Bugun Fed one cikti.",
        "[PORTFOLIO] Bugun TSLA one cikti.",
        "[NEWS] Bugun Meclis one cikti.",
        "[SPORTS] Bugun Arsenal one cikti.",
    ]


def test_the_terminal_report_keeps_the_turkish_the_sms_gives_up(
    world: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """The fold is the SMS transport's problem, not the summary's."""
    main([])

    printed = capsys.readouterr().out
    assert "=== MARKETS ===\nBugün Fed öne çıktı." in printed
    assert printed.count("öne çıktı") == 4


def test_a_dead_source_costs_only_its_own_category(
    world: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """Finnhub is down, so markets has no data — and the other three still arrive.

    The markets SMS is still sent. A silent category would be indistinguishable
    from a quiet news day, which is the whole reason the fetcher degrades to an
    empty list instead of raising.
    """
    world.reset()
    world.add(responses.GET, FINNHUB_NEWS_URL, status=500)
    world.add(responses.GET, FOOTBALL_MATCHES_URL, status=500)
    world.add(responses.GET, TRIGGER_URL, body="ok")

    assert main([]) == 0

    markets, portfolio, news, sports = _sent_messages(world)
    assert markets == "[MARKETS] Bugun icin veri yok."
    assert sports == "[SPORTS] Bugun kayda deger bir sonuc yok."
    assert portfolio == "[PORTFOLIO] Bugun TSLA one cikti."
    assert news == "[NEWS] Bugun Meclis one cikti."


def test_dry_run_builds_the_whole_report_and_still_sends_nothing(
    world: responses.RequestsMock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--dry-run"]) == 0

    assert _sent_messages(world) == []
    assert capsys.readouterr().out.count("öne çıktı") == 4


def test_a_relay_failure_turns_the_run_red_without_losing_the_report(
    world: responses.RequestsMock,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The exit code is what makes a silent phone visible to the scheduled job."""
    world.reset()
    world.add(responses.GET, FINNHUB_NEWS_URL, json=[])
    world.add(responses.GET, FOOTBALL_MATCHES_URL, json={"matches": []})
    world.add(responses.GET, TRIGGER_URL, status=502)

    with caplog.at_level(logging.INFO, logger="app"):
        assert main([]) == 1

    assert "=== PORTFOLIO ===" in capsys.readouterr().out
    assert "SMS relay accepted 0/4" in caplog.text


def test_the_run_log_accounts_for_every_category(
    world: responses.RequestsMock, caplog: pytest.LogCaptureFixture
) -> None:
    """All that survives a scheduled run, once stdout has gone to /dev/null.

    Spelled out in full rather than probed line by line, because the value of
    this log is that nothing is missing from it.
    """
    with caplog.at_level(logging.INFO, logger="app"):
        main([])

    assert [record.getMessage() for record in caplog.records] == [
        "MARKETS ok in 0.0s, 20 chars.",
        "PORTFOLIO ok in 0.0s, 21 chars.",
        "NEWS ok in 0.0s, 23 chars.",
        "SPORTS ok in 0.0s, 24 chars.",
        "SMS relay accepted all 4 categories.",
    ]
