# TASKS.md — Task Backlog

This file lists the discrete units of work the Agent Loop (see `AGENTS.md`) works through. Each task should be sized to a single PR. When an agent finishes a task, it checks the box and adds notes if useful.

## Phase 0 — Skeleton (Done)
- [x] TASK-000: Project skeleton — directory structure, `pyproject.toml`, `.gitignore`, pre-commit, CI, `AGENTS.md`/`PLAN.md`/`TASKS.md`, example `config.py` module + tests.

## Phase 1 — Fetch + Summarize + Terminal Output (current focus)
No SMS, no AWS in this phase. Goal: run `python -m app.main` and see all 4 category summaries printed to the terminal.

- [ ] TASK-001: `src/app/fetchers/portfolio.py` — use yfinance to fetch closing price and % change for each symbol in `config/portfolio.json`.
  - Acceptance: a missing/invalid symbol doesn't raise, it's marked as "no data"; tests mock the yfinance call.
- [ ] TASK-002: `src/app/fetchers/market_news.py` — fetch global market headlines from Finnhub/Alpha Vantage.
  - Acceptance: an API error returns an empty list + logs a warning, never raises.
- [ ] TASK-003: `src/app/fetchers/general_news.py` — fetch TR + global headlines via RSS (AA, Reuters World).
  - Acceptance: feedparser calls are mocked in tests; a broken/unreachable feed doesn't take down the run.
- [ ] TASK-004: `src/app/fetchers/sports.py` — fetch results from API-Football (4 leagues), balldontlie.io (NBA), Ergast (F1).
  - Acceptance: off-season / no matches returns "nothing notable today" instead of an empty/awkward output.
- [ ] TASK-005: `src/app/summarizer.py` — call the Claude API with a category-specific prompt to turn raw fetcher output into a short summary.
  - Acceptance: one prompt template per category; the Anthropic API call is mocked in tests; output length stays within a sane bound (see `PLAN.md` §5).
- [ ] TASK-006: `src/app/main.py` — CLI entrypoint. Calls all 4 fetchers, summarizes each, prints the result to the terminal grouped by category (see `PLAN.md` §6 for the output format). Each category wrapped in try/except so one failure doesn't stop the others.
  - Acceptance: running `python -m app.main` with all external calls mocked produces a full 4-section printed report in a test.

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
