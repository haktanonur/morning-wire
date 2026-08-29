from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from app.fetchers.portfolio import PortfolioConfigError
from app.main import Section, build_report, delivery_summary, main, render
from app.sender import SendOutcome
from app.summarizer import SummarizationError

CATEGORY_PATCHES = {
    "MARKETS": ("app.main.fetch_market_news", "app.main.summarize_markets"),
    "PORTFOLIO": ("app.main.load_portfolio", "app.main.summarize_portfolio"),
    "NEWS": ("app.main.fetch_general_news", "app.main.summarize_news"),
    "SPORTS": ("app.main.fetch_sports", "app.main.summarize_sports"),
}


@pytest.fixture(autouse=True)
def _no_external_calls(mocker: MockerFixture) -> None:
    """Mock every fetcher and summarizer so no test can reach the network."""
    for fetch_target, summarize_target in CATEGORY_PATCHES.values():
        mocker.patch(fetch_target, return_value=["raw"])
        mocker.patch(summarize_target, return_value="A tidy summary.")
    mocker.patch("app.main.fetch_portfolio_prices", return_value=["raw"])


@pytest.fixture
def send(mocker: MockerFixture) -> MagicMock:
    """Stub the SMS relay, accepting every category."""
    return mocker.patch(
        "app.main.send_report",
        return_value=tuple(SendOutcome(heading=heading) for heading in CATEGORY_PATCHES),
    )


def test_build_report_returns_all_four_categories_in_order() -> None:
    assert [section.heading for section in build_report()] == [
        "MARKETS",
        "PORTFOLIO",
        "NEWS",
        "SPORTS",
    ]


def test_build_report_fills_every_section_with_its_summary() -> None:
    assert all(section.body == "A tidy summary." for section in build_report())


@pytest.mark.parametrize("failing", sorted(CATEGORY_PATCHES))
def test_build_report_isolates_a_failing_fetcher(failing: str, mocker: MockerFixture) -> None:
    mocker.patch(CATEGORY_PATCHES[failing][0], side_effect=RuntimeError("source is down"))

    sections = {section.heading: section.body for section in build_report()}

    assert sections[failing] == "[unavailable: source is down]"
    assert [body for heading, body in sections.items() if heading != failing] == [
        "A tidy summary."
    ] * 3


def test_build_report_isolates_a_failing_summarizer(mocker: MockerFixture) -> None:
    mocker.patch(
        "app.main.summarize_news",
        side_effect=SummarizationError("Claude API call failed (APIStatusError)"),
    )

    sections = {section.heading: section.body for section in build_report()}

    assert sections["NEWS"] == "[unavailable: Claude API call failed (APIStatusError)]"
    assert sections["MARKETS"] == "A tidy summary."


def test_build_report_surfaces_a_missing_portfolio_config(mocker: MockerFixture) -> None:
    mocker.patch(
        "app.main.load_portfolio",
        side_effect=PortfolioConfigError("config/portfolio.json not found"),
    )

    sections = {section.heading: section.body for section in build_report()}

    assert sections["PORTFOLIO"] == "[unavailable: config/portfolio.json not found]"


def test_build_report_falls_back_to_the_exception_type_when_it_has_no_message(
    mocker: MockerFixture,
) -> None:
    mocker.patch("app.main.fetch_sports", side_effect=TimeoutError())

    sections = {section.heading: section.body for section in build_report()}

    assert sections["SPORTS"] == "[unavailable: TimeoutError]"


def test_render_uses_the_plan_output_format() -> None:
    report = render([Section("MARKETS", "Up."), Section("SPORTS", "Nothing.")])

    assert report == "=== MARKETS ===\nUp.\n\n=== SPORTS ===\nNothing."


def test_main_prints_a_full_four_section_report(
    send: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    """`main()` is exactly what `python -m app.main` runs, with everything mocked."""
    main([])

    printed = capsys.readouterr().out
    for heading in CATEGORY_PATCHES:
        assert f"=== {heading} ===" in printed
    assert printed.count("A tidy summary.") == 4


# --- sending ----------------------------------------------------------------


def test_main_sends_every_section_by_default(send: MagicMock) -> None:
    """Sending is the default because the scheduled run passes no arguments."""
    assert main([]) == 0

    (sections,) = send.call_args.args
    assert list(sections) == [(heading, "A tidy summary.") for heading in CATEGORY_PATCHES]


def test_main_sends_a_failed_category_as_its_unavailable_body(
    send: MagicMock, mocker: MockerFixture
) -> None:
    """A dead source still owes the reader an SMS saying so."""
    mocker.patch("app.main.fetch_sports", side_effect=RuntimeError("source is down"))

    main([])

    (sections,) = send.call_args.args
    assert ("SPORTS", "[unavailable: source is down]") in list(sections)


def test_main_reports_the_delivery_outcome_on_stderr(
    send: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    main([])

    assert "accepted all 4" in capsys.readouterr().err


def test_main_exits_non_zero_when_a_category_does_not_reach_the_relay(send: MagicMock) -> None:
    """The exit code is a scheduled run's only failure signal."""
    send.return_value = (
        SendOutcome(heading="MARKETS"),
        SendOutcome(heading="PORTFOLIO", error="ConnectionError"),
    )

    assert main([]) == 1


def test_main_still_prints_the_report_when_delivery_fails(
    send: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    send.return_value = (SendOutcome(heading="MARKETS", error="ConnectionError"),)

    main([])

    assert "=== MARKETS ===" in capsys.readouterr().out


# --- dry run ----------------------------------------------------------------


def test_dry_run_sends_nothing(send: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--dry-run"]) == 0

    send.assert_not_called()
    assert "=== MARKETS ===" in capsys.readouterr().out


def test_dry_run_does_not_need_the_trigger_url(capsys: pytest.CaptureFixture[str]) -> None:
    """No `send` fixture here: a dry run must work with no SMS credentials configured."""
    assert main(["--dry-run"]) == 0
    assert "=== SPORTS ===" in capsys.readouterr().out


def test_delivery_summary_names_only_the_refused_categories() -> None:
    summary = delivery_summary(
        [
            SendOutcome(heading="MARKETS"),
            SendOutcome(heading="PORTFOLIO", error="HTTPError"),
        ]
    )

    assert summary == "SMS relay accepted 1/2; refused: PORTFOLIO."
    assert "HTTPError" not in summary
