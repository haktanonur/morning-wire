# TASKS.md — Task Backlog

This file lists the discrete units of work the Agent Loop (see `AGENTS.md`) works through. Each task should be sized to a single PR. When an agent finishes a task, it checks the box and adds notes if useful.

## Phase 0 — Skeleton (Done)
- [x] TASK-000: Project skeleton — directory structure, `pyproject.toml`, `.gitignore`, pre-commit, CI, `AGENTS.md`/`PLAN.md`/`TASKS.md`, example `config.py` module + tests.

## Phase 1 — Fetch + Summarize + Terminal Output (Done)
No SMS, no AWS in this phase. Goal: run `python -m app.main` and see all 4 category summaries printed to the terminal.

- [x] TASK-001: `src/app/fetchers/portfolio.py` — use yfinance to fetch closing price and % change for each symbol in `config/portfolio.json`.
  - Acceptance: a missing/invalid symbol doesn't raise, it's marked as "no data"; tests mock the yfinance call.
  - Notes: split into `load_portfolio()` (file IO) and `fetch_portfolio_prices()` (network IO) so `main.py` composes them in TASK-006. A "no data" symbol is a `PortfolioQuote` with `close=None` rather than a dropped entry, so the summarizer can still name it. A missing/malformed `config/portfolio.json` raises `PortfolioConfigError` (no silent fallback to the example file) — TASK-006's per-category try/except turns that into `[unavailable: ...]`. Uses a 5-day history window so weekends/holidays still yield a previous close.
- [x] TASK-002: `src/app/fetchers/market_news.py` — fetch global market headlines from Finnhub/Alpha Vantage.
  - Acceptance: an API error returns an empty list + logs a warning, never raises.
  - Notes: Finnhub only — the Alpha Vantage fallback in `docs/data-sources.md` is deliberately **not** implemented; add it as its own task if Finnhub's free tier proves unreliable. The API key goes in an `X-Finnhub-Token` header rather than a `token` query param, because request URLs leak into exception messages and logs; a test asserts the key never reaches the log output. `config.py` now calls `load_dotenv()` on import (it was declared as a dependency but never called, so `.env` was silently ignored). Finnhub's only relevant category is `general`, which mixes real macro/market stories with general world news — filtering that down is TASK-005's prompt problem, not the fetcher's.
- [x] TASK-003: `src/app/fetchers/general_news.py` — fetch TR + global headlines via RSS (AA, Reuters World).
  - Acceptance: feedparser calls are mocked in tests; a broken/unreachable feed doesn't take down the run.
  - Notes: **Reuters' public RSS is dead** — the endpoint named in `PLAN.md` §4 and `docs/data-sources.md` returns 0 entries (verified live), so BBC World replaces it as the global feed. Owner chose a single global source rather than BBC + Al Jazeera. TR side is AA Gündem + AA Ekonomi. Each `Article` carries a `region` (`TR`/`WORLD`) so TASK-005 can keep the two halves of the category apart. Feeds are polled independently, so one dead feed costs only its own headlines. `feedparser.parse()` reports transport failures through `status`/`bozo` rather than raising, so both are inspected explicitly; `bozo` alone is not fatal because it is also set for merely untidy feeds. Two follow-ups: `PLAN.md` §4 and `docs/data-sources.md` still name Reuters and are now stale, and AA Gündem mixes sports stories into general news, so TASK-005's prompt has to de-duplicate against the sports category.
- [x] TASK-004: `src/app/fetchers/sports.py` — fetch results from API-Football (4 leagues), balldontlie.io (NBA), Ergast (F1).
  - Acceptance: off-season / no matches returns "nothing notable today" instead of an empty/awkward output.
  - Notes: **all three planned sources were dead or paywalled** (verified live). API-Football's free plan refuses the current season (`"Free plans do not have access to this season, try from 2022 to 2024"`) → replaced by **football-data.org**, whose free tier covers PL, La Liga and Serie A but **not the Turkish Süper Lig** — dropped by owner decision. Ergast returns 403 (Cloudflare) → replaced by **Jolpica**, a keyless Ergast-compatible mirror. balldontlie now requires a key → **NBA dropped from the category** by owner decision. Both sources are filtered to a recency window: the F1 endpoint always returns the last race that happened, so without it a race from before the summer break would be re-reported every morning. `SportsReport.has_results` being false is the off-season signal; the `NOTHING_NOTABLE` constant is what TASK-005/006 should render then. `today` is injectable on every function so date-window tests are deterministic. **F1 was later dropped by owner decision**, which took the Jolpica source, the `RaceResult`/`DriverResult` types and the `SportsReport` wrapper with it — `fetch_sports()` now returns a plain tuple of `MatchResult`, and an empty tuple is the off-season signal that renders as `NOTHING_NOTABLE`. The category is football only.
- [x] TASK-005: `src/app/summarizer.py` — call the Claude API with a category-specific prompt to turn raw fetcher output into a short summary.
  - Acceptance: one prompt template per category; the Anthropic API call is mocked in tests; output length stays within a sane bound (see `PLAN.md` §5).
  - Inherited from earlier tasks — the fetchers deliberately do not filter, so the prompts must: (a) Finnhub's `general` category mixes macro/market stories with general world news, so the markets prompt has to ignore the non-market ones; (b) AA Gündem carries sports stories, so the news prompt must not restate what the sports category already covers; (c) `Article.region` is `TR` or `WORLD`, so the news prompt can cover both halves without blending them.
  - Notes: unlike the fetchers, these functions **do** raise (`SummarizationError`) — a fetcher returning nothing is a normal outcome the summary can describe, but a failed API call leaves nothing to print, so TASK-006 needs an exception to turn into `[unavailable: ...]`. Only the exception *type* goes into the message, so a provider error can never carry the API key into a log. Empty input short-circuits to `NO_DATA` (or `NOTHING_NOTABLE` for sports) without spending an API call. Length is capped at `MAX_SUMMARY_CHARS = 600` now rather than after Phase 2, since SMS segments are the real constraint; `_trim` cuts on `". "` rather than `"."` because a decimal point in a price was being read as a sentence end. Three prompt fixes came out of live runs, not tests: the model announced *absent* data ("No Formula 1 results were provided"), leaked AA's sports stories into the news section, and dropped the world half entirely because the feed is 16 TR vs 8 WORLD — the news prompt now demands exactly two sentences per region.
- [x] TASK-006: `src/app/main.py` — CLI entrypoint. Calls all 4 fetchers, summarizes each, prints the result to the terminal grouped by category (see `PLAN.md` §6 for the output format). Each category wrapped in try/except so one failure doesn't stop the others.
  - Acceptance: running `python -m app.main` with all external calls mocked produces a full 4-section printed report in a test.
  - Notes: `build_section()` is the single error-isolation boundary — nothing a fetcher or the summarizer raises gets past it. The `[unavailable: ...]` reason is `str(exc)` falling back to the exception type, which is why `summarizer.py` sanitizes its own message rather than leaving that to `main.py`. The report goes to stdout and warnings to stderr, so the output stays pipeable. A `runpy.run_module` test for the literal `python -m` path was written and then **removed**: `run_module` re-executes the module, so the mocks bound to the already-imported `app.main` don't apply and the test silently hit the real network (4.2s of the suite's runtime). `main()` is what the `__main__` guard calls, so testing `main()` directly covers the same path honestly. The end-to-end run also caught a summarizer regression: naming Formula 1 in `SPORTS_PROMPT` made the model report its *absence* on race-free weeks, so the prompt now names no sport at all and just follows the data.

## Phase 2 — SMS Delivery (Twilio)
- [ ] TASK-007: `src/app/sender.py` — send a category-tagged SMS via Twilio.
  - Acceptance: a send failure for one category doesn't block the others; Twilio calls are mocked in tests.
- [ ] TASK-008: Update `main.py` with a `--dry-run` flag — default behavior sends real SMS via `sender.py`; `--dry-run` reuses the Phase 1 terminal-print path instead.

## Phase 3 — Lambda Orchestration
- [ ] TASK-009: `src/app/lambda_handler.py` — thin wrapper that calls into `main.py`'s logic from an AWS Lambda handler.

## Phase 4 — AWS Deployment
- [ ] TASK-010: Lambda packaging script or AWS SAM/CDK template (dependencies + code).
- [ ] TASK-011: EventBridge cron rule (daily 08:00 Istanbul time, expressed as UTC cron).
- [ ] TASK-012: Docs + deploy script for Secrets Manager / Lambda env vars.

## Phase 5 — Hardening
- [ ] TASK-013: Standardize CloudWatch log format (which category, how long it took, success/failure).
- [ ] TASK-014: End-to-end dry-run integration test covering the full pipeline.
- [ ] TASK-015: Update README with deployment steps.

## Open Decisions
- [ ] Real portfolio symbol list (`config/portfolio.json` — gitignored, real holdings)
- [ ] SMS send time for Phase 2 (default assumption: 08:00 Istanbul time)
- [ ] SMS category order for Phase 2 (default assumption: markets → portfolio → news → sports)
