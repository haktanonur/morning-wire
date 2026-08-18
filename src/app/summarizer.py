"""Turn raw fetcher output into short per-category summaries via the Claude API.

One prompt template per category, as required by ``PLAN.md`` §5. The prompts do
the filtering the fetchers deliberately skipped: Finnhub's ``general`` feed
mixes macro stories with general world news, and AA Gündem carries sports
stories that the sports category already covers.

Unlike the fetchers, these functions *do* raise. A fetcher returning nothing is
a normal outcome the summary can describe, but a failed API call leaves nothing
to print, so ``main.py`` (TASK-006) catches ``SummarizationError`` and renders
that category as ``[unavailable: ...]``.
"""

from __future__ import annotations

import logging
from typing import Any

import anthropic

from app.config import load_anthropic_settings
from app.fetchers.general_news import REGION_TR, Article
from app.fetchers.market_news import Headline
from app.fetchers.portfolio import PortfolioQuote
from app.fetchers.sports import NOTHING_NOTABLE, MatchResult

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

# Phase 1 prints to a terminal, but Phase 2 has to fit these into SMS segments,
# so the length is capped now rather than after the prompts are tuned.
#
# 400 comes off the segment arithmetic rather than taste. Once sms_text.to_gsm7
# has folded the Turkish letters, a concatenated segment carries 153 characters,
# so three of them hold 459 — 400 keeps a category inside three segments with
# room left for the tag sender.py (TASK-007) puts in front of it. Measured
# against real feeds that is about 11 segments a day across the four categories,
# against 28 for the same Turkish text left at 600 characters and unfolded.
MAX_TOKENS = 400
MAX_SUMMARY_CHARS = 400

NO_DATA = "Bugün için veri yok."

# The prompts stay in English (AGENTS.md keeps code English) but ask for Turkish
# output, because the brief is delivered by SMS to a Turkish reader.
SYSTEM_PROMPT = (
    "You write one section of a personal morning briefing. Reply in TURKISH, in "
    "2-4 plain sentences of prose: no headings, no bullet points, no markdown, no "
    "preamble such as 'İşte özetiniz'. Keep the whole reply under 400 characters. "
    "Report only what the supplied data says and never invent a number, name or "
    "event that is not in it. Never point out that something is missing from the "
    "data — just leave it out. Give no investment advice or recommendations."
)

MARKETS_PROMPT = (
    "Summarize today's economy and global markets from the headlines below. "
    "The feed is a general news wire, so ignore anything that is not about "
    "markets, central banks, inflation, rates, commodities or FX. Lead with the "
    "story that matters most to an investor."
)

PORTFOLIO_PROMPT = (
    "Summarize the state of this portfolio from the closing prices below. Say "
    "which holdings rose and which fell and roughly by how much, and call out "
    "anything unusually large. Name any holding marked 'no data' as unavailable "
    "rather than skipping it silently."
)

NEWS_PROMPT = (
    "Summarize the day's current events from the headlines below. Your reply must "
    "be exactly three sentences, structured like this and overriding any other "
    "sentence count:\n"
    "1. A sentence on the TURKEY headlines.\n"
    "2. A second sentence on the TURKEY headlines.\n"
    "3. A sentence on the WORLD headlines, combining several of them if needed.\n"
    "Sentence 3 is mandatory. The feed carries twice as many Turkish headlines as "
    "world ones, which is not a reason to spend all three sentences on Turkey. "
    "Keep every sentence under 120 characters: a reply that overruns is trimmed at "
    "a sentence boundary, and sentence 3 is the one that would be lost.\n"
    "Ignore every sports headline — any league, club, national team, athlete, "
    "tournament, qualifier or ranking, in any sport — because a separate sports "
    "section already covers them. Prefer politics, economics and society over "
    "routine administrative notices."
)

SPORTS_PROMPT = (
    "Summarize the football results below, in the order they appear. Give the "
    "scores plainly and write about nothing beyond what is listed — do not "
    "speculate about standings or form."
)


class SummarizationError(RuntimeError):
    """Raised when the Claude API could not produce a usable summary."""


def _format_headlines(headlines: list[Headline]) -> str:
    """Render market headlines as one line per story."""
    return "\n".join(
        f"- {headline.title}"
        + (f" ({headline.source})" if headline.source else "")
        + (f" — {headline.summary}" if headline.summary else "")
        for headline in headlines
    )


def _format_quotes(quotes: list[PortfolioQuote]) -> str:
    """Render portfolio quotes as one line per holding, including missing ones."""
    lines = []
    for quote in quotes:
        if quote.close is None or quote.change_pct is None:
            lines.append(f"- {quote.label} ({quote.ticker}): no data")
        else:
            lines.append(
                f"- {quote.label} ({quote.ticker}): close {quote.close:.2f}, "
                f"change {quote.change_pct:+.2f}%"
            )
    return "\n".join(lines)


def _format_articles(articles: list[Article]) -> str:
    """Render news articles grouped by region so the prompt can keep them apart."""
    turkish = [article for article in articles if article.region == REGION_TR]
    world = [article for article in articles if article.region != REGION_TR]

    sections = []
    for label, group in (("TURKEY", turkish), ("WORLD", world)):
        if group:
            body = "\n".join(f"- {article.title} ({article.source})" for article in group)
            sections.append(f"{label}:\n{body}")
    return "\n\n".join(sections)


def _format_matches(matches: tuple[MatchResult, ...]) -> str:
    """Render football results as one line per match."""
    return "\n".join(
        f"- {match.competition}: {match.home_team} {match.home_score}-"
        f"{match.away_score} {match.away_team} ({match.played_on.isoformat()})"
        for match in matches
    )


def _extract_text(message: Any) -> str:
    """Pull the text blocks out of a Claude response and join them."""
    blocks = getattr(message, "content", None)
    if not isinstance(blocks, list):
        return ""
    return "".join(
        block.text
        for block in blocks
        if getattr(block, "type", None) == "text" and isinstance(getattr(block, "text", None), str)
    ).strip()


def _trim(summary: str) -> str:
    """Cap the summary at MAX_SUMMARY_CHARS, preferring a sentence boundary.

    The boundary is ``". "`` rather than ``"."`` so that a decimal point in a
    price or percentage is not mistaken for the end of a sentence.

    This is a backstop, not the primary length control — the prompts are. It
    logs when it fires because dropping the final sentence is invisible in the
    output: an overlong news summary once lost its world half here, and the
    missing half looked exactly like the model ignoring the prompt.
    """
    if len(summary) <= MAX_SUMMARY_CHARS:
        return summary

    logger.warning(
        "Summary ran to %d characters, over the %d cap; trimming may drop its last sentence.",
        len(summary),
        MAX_SUMMARY_CHARS,
    )
    cutoff = summary.rfind(". ", 0, MAX_SUMMARY_CHARS)
    if cutoff == -1:
        return summary[:MAX_SUMMARY_CHARS].rstrip()
    return summary[: cutoff + 1]


def _summarize(prompt: str, data: str) -> str:
    """Send one category's prompt and data to Claude and return the summary text.

    Args:
        prompt: The category-specific instruction.
        data: The rendered fetcher output.

    Returns:
        The summary, trimmed to ``MAX_SUMMARY_CHARS``.

    Raises:
        SummarizationError: If the API key is missing, the call fails, or the
            response carries no text. Only the exception type is reported, so a
            provider error message can never carry the API key into a log.
    """
    try:
        settings = load_anthropic_settings()
        client = anthropic.Anthropic(api_key=settings.api_key)
        message = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"{prompt}\n\n{data}"}],
        )
    except Exception as exc:
        raise SummarizationError(f"Claude API call failed ({type(exc).__name__})") from exc

    text = _extract_text(message)
    if not text:
        raise SummarizationError("Claude returned an empty summary")
    return _trim(text)


def summarize_markets(headlines: list[Headline]) -> str:
    """Summarize the economy and global markets category."""
    if not headlines:
        return NO_DATA
    return _summarize(MARKETS_PROMPT, _format_headlines(headlines))


def summarize_portfolio(quotes: list[PortfolioQuote]) -> str:
    """Summarize the portfolio category."""
    if not quotes:
        return NO_DATA
    return _summarize(PORTFOLIO_PROMPT, _format_quotes(quotes))


def summarize_news(articles: list[Article]) -> str:
    """Summarize the Turkey + world current events category."""
    if not articles:
        return NO_DATA
    return _summarize(NEWS_PROMPT, _format_articles(articles))


def summarize_sports(matches: tuple[MatchResult, ...]) -> str:
    """Summarize the sports category.

    An off-season run with no fixtures is a normal outcome, so it short-circuits
    to ``NOTHING_NOTABLE`` instead of asking Claude to describe an empty list.
    """
    if not matches:
        return NOTHING_NOTABLE
    return _summarize(SPORTS_PROMPT, _format_matches(matches))
