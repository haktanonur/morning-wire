from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from pytest_mock import MockerFixture

from app.fetchers.general_news import REGION_TR, REGION_WORLD, Article
from app.fetchers.market_news import Headline
from app.fetchers.portfolio import PortfolioQuote
from app.fetchers.sports import (
    NOTHING_NOTABLE,
    DriverResult,
    MatchResult,
    RaceResult,
    SportsReport,
)
from app.summarizer import (
    MAX_SUMMARY_CHARS,
    MODEL,
    NO_DATA,
    SummarizationError,
    summarize_markets,
    summarize_news,
    summarize_portfolio,
    summarize_sports,
)

API_KEY = "sk-fake-anthropic-key-abc123"


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test a known key so nothing can fall through to the real .env."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", API_KEY)


def _reply(text: str) -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


@pytest.fixture
def create(mocker: MockerFixture) -> Any:
    """Patch the Anthropic client so no test can reach the real API."""
    create = mocker.Mock(return_value=_reply("A tidy summary."))
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    mocker.patch("app.summarizer.anthropic.Anthropic", return_value=client)
    return create


def _headline(**overrides: Any) -> Headline:
    fields: dict[str, Any] = {
        "title": "Fed holds rates steady",
        "source": "Reuters",
        "url": "https://example.com/fed",
        "summary": "The Federal Reserve left rates unchanged.",
        "published_at": datetime(2026, 8, 17, tzinfo=UTC),
    }
    fields.update(overrides)
    return Headline(**fields)


def _article(**overrides: Any) -> Article:
    fields: dict[str, Any] = {
        "title": "Meclis bütçeyi görüştü",
        "source": "Anadolu Ajansı (Gündem)",
        "url": "https://example.com/tr",
        "summary": "",
        "published_at": None,
        "region": REGION_TR,
    }
    fields.update(overrides)
    return Article(**fields)


def _sports_report() -> SportsReport:
    return SportsReport(
        matches=(
            MatchResult(
                competition="Premier League",
                home_team="Arsenal FC",
                away_team="Chelsea FC",
                home_score=2,
                away_score=1,
                played_on=date(2026, 8, 16),
            ),
        ),
        race=RaceResult(
            name="Hungarian Grand Prix",
            race_date=date(2026, 8, 16),
            podium=(DriverResult(position=1, driver="Lando Norris", constructor="McLaren"),),
        ),
    )


def _sent_prompt(create: Any) -> str:
    return str(create.call_args.kwargs["messages"][0]["content"])


# --- empty input short-circuits --------------------------------------------


def test_summarize_markets_returns_no_data_without_calling_the_api(create: Any) -> None:
    assert summarize_markets([]) == NO_DATA
    create.assert_not_called()


def test_summarize_portfolio_returns_no_data_without_calling_the_api(create: Any) -> None:
    assert summarize_portfolio([]) == NO_DATA
    create.assert_not_called()


def test_summarize_news_returns_no_data_without_calling_the_api(create: Any) -> None:
    assert summarize_news([]) == NO_DATA
    create.assert_not_called()


def test_summarize_sports_returns_nothing_notable_in_the_off_season(create: Any) -> None:
    assert summarize_sports(SportsReport(matches=(), race=None)) == NOTHING_NOTABLE
    create.assert_not_called()


# --- per-category prompts ---------------------------------------------------


def test_summarize_markets_sends_headlines_and_returns_the_summary(create: Any) -> None:
    assert summarize_markets([_headline()]) == "A tidy summary."

    prompt = _sent_prompt(create)
    assert "Fed holds rates steady" in prompt
    assert "Reuters" in prompt
    assert "not about markets" in prompt


def test_summarize_portfolio_renders_prices_and_missing_symbols(create: Any) -> None:
    summarize_portfolio(
        [
            PortfolioQuote(ticker="TSLA", label="Tesla", close=250.1, change_pct=-1.234),
            PortfolioQuote(ticker="GC=F", label="Gold (USD/oz)", close=None, change_pct=None),
        ]
    )

    prompt = _sent_prompt(create)
    assert "Tesla (TSLA): close 250.10, change -1.23%" in prompt
    assert "Gold (USD/oz) (GC=F): no data" in prompt


def test_summarize_news_groups_the_two_regions_separately(create: Any) -> None:
    summarize_news(
        [
            _article(),
            _article(title="Global summit opens", source="BBC World", region=REGION_WORLD),
        ]
    )

    prompt = _sent_prompt(create)
    assert "TURKEY:" in prompt
    assert "WORLD:" in prompt
    assert prompt.index("TURKEY:") < prompt.index("WORLD:")
    assert "Ignore every sports headline" in prompt


def test_summarize_news_omits_a_region_with_no_articles(create: Any) -> None:
    summarize_news([_article(title="Global summit opens", region=REGION_WORLD)])

    prompt = _sent_prompt(create)
    assert "WORLD:" in prompt
    assert "TURKEY:" not in prompt


def test_summarize_sports_renders_scores_and_the_podium(create: Any) -> None:
    summarize_sports(_sports_report())

    prompt = _sent_prompt(create)
    assert "Premier League: Arsenal FC 2-1 Chelsea FC (2026-08-16)" in prompt
    assert "Hungarian Grand Prix, 2026-08-16" in prompt
    assert "1. Lando Norris (McLaren)" in prompt


def test_summarize_sports_handles_football_only(create: Any) -> None:
    summarize_sports(SportsReport(matches=_sports_report().matches, race=None))

    prompt = _sent_prompt(create)
    assert "FOOTBALL:" in prompt
    assert "FORMULA 1" not in prompt


def test_summarize_sports_handles_f1_only(create: Any) -> None:
    summarize_sports(SportsReport(matches=(), race=_sports_report().race))

    prompt = _sent_prompt(create)
    assert "FOOTBALL:" not in prompt
    assert "FORMULA 1" in prompt


# --- shared API behaviour ---------------------------------------------------


def test_summarize_uses_the_haiku_model_and_a_token_cap(create: Any) -> None:
    summarize_markets([_headline()])

    kwargs = create.call_args.kwargs
    assert kwargs["model"] == MODEL
    assert kwargs["max_tokens"] > 0
    assert "no headings" in kwargs["system"]


def test_summarize_trims_an_overlong_summary_at_a_sentence_boundary(create: Any) -> None:
    sentence = "This sentence is padding for the length cap. "
    create.return_value = _reply(sentence * 40)

    summary = summarize_markets([_headline()])

    assert len(summary) <= MAX_SUMMARY_CHARS
    assert summary.endswith(".")


def test_summarize_does_not_trim_at_a_decimal_point(create: Any) -> None:
    """A price like '0.21%' must not be read as the end of a sentence."""
    prices = "gold rose 2.14% then silver rose 1.51% then copper rose 3.75% " * 20
    create.return_value = _reply(f"The desk noted the shift. Overnight {prices}")

    summary = summarize_portfolio([PortfolioQuote("TSLA", "Tesla", 250.1, -1.2)])

    assert len(summary) <= MAX_SUMMARY_CHARS
    assert summary == "The desk noted the shift."


def test_summarize_trims_an_overlong_summary_without_any_sentence_boundary(create: Any) -> None:
    create.return_value = _reply("x" * (MAX_SUMMARY_CHARS + 100))

    assert len(summarize_markets([_headline()])) == MAX_SUMMARY_CHARS


def test_summarize_joins_multiple_text_blocks(create: Any) -> None:
    create.return_value = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text="First half. "),
            SimpleNamespace(type="thinking", thinking="ignored"),
            SimpleNamespace(type="text", text="Second half."),
        ]
    )

    assert summarize_markets([_headline()]) == "First half. Second half."


def test_summarize_raises_when_the_api_call_fails(create: Any) -> None:
    create.side_effect = RuntimeError("upstream exploded")

    with pytest.raises(SummarizationError, match="RuntimeError"):
        summarize_markets([_headline()])


def test_summarize_raises_when_the_api_key_is_missing(
    create: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(SummarizationError):
        summarize_markets([_headline()])

    create.assert_not_called()


@pytest.mark.parametrize(
    "content",
    [[], [SimpleNamespace(type="text", text="   ")], [SimpleNamespace(type="thinking")], None],
)
def test_summarize_raises_when_the_response_carries_no_text(create: Any, content: Any) -> None:
    create.return_value = SimpleNamespace(content=content)

    with pytest.raises(SummarizationError, match="empty summary"):
        summarize_markets([_headline()])


def test_summarize_error_does_not_leak_the_api_key(create: Any) -> None:
    """Provider errors can quote the request; only the exception type is reported."""
    create.side_effect = RuntimeError(f"401 unauthorized for key {API_KEY}")

    with pytest.raises(SummarizationError) as excinfo:
        summarize_markets([_headline()])

    assert API_KEY not in str(excinfo.value)
