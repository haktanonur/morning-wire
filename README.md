# Daily Brief Bot

A personal daily-briefing tool. Fetches data for 4 categories — global markets, personal portfolio, TR + global news, and sports — summarizes each with the Claude API, and (in the current phase) prints the result to the terminal. A later phase adds SMS delivery via a MacroDroid webhook on the owner's own phone, and AWS Lambda deployment.

## Read First
- [`CLAUDE.md`](./CLAUDE.md) / [`AGENTS.md`](./AGENTS.md) — rules every coding agent must follow in this repo, plus the Agent Loop
- [`PLAN.md`](./PLAN.md) — architecture, categories, phases
- [`TASKS.md`](./TASKS.md) — task backlog (work through this in order)
- [`docs/architecture.md`](./docs/architecture.md) — component diagram
- [`docs/data-sources.md`](./docs/data-sources.md) — APIs used and their limits

## Current Milestone: Phase 1
Fetch + summarize + print to terminal. No SMS, no AWS yet. See `TASKS.md` for the exact task list.

## Local Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
cp config/portfolio.example.json config/portfolio.json  # then enter your real symbols
```

Then create a gitignored `.env` in the repo root with the keys below. `src/app/config.py` is the only module that reads them.

| Variable | Needed for | Phase |
|---|---|---|
| `ANTHROPIC_API_KEY` | `summarizer.py` | 1 |
| `FINNHUB_API_KEY` | `fetchers/market_news.py` | 1 |
| `FOOTBALL_DATA_API_KEY` | `fetchers/sports.py` — free key from football-data.org | 1 |
| `MACRODROID_TRIGGER_URL` | `sender.py` — the webhook URL of the SMS macro on your phone | 2 |

`fetchers/portfolio.py` (yfinance) needs no key.

## Running Tests
```bash
pytest
ruff check .
mypy src
```

## Running Locally
```bash
python -m app.main --dry-run   # print the briefing, send nothing
python -m app.main             # print it and send one SMS per category
```
Both fetch all 4 categories, summarize each, and print the result to the terminal. Each category is isolated — if one fails, the others still print, and the failure is sent as `[unavailable: ...]` rather than silently dropped.

Sending is the default because the scheduled run passes no arguments; `--dry-run` is the developer's flag, and it needs no `MACRODROID_TRIGGER_URL`. A send run exits `1` if any category failed to reach the relay — that exit code is the only failure signal the scheduled job has.

## Getting Started With Claude Code
Open this repo in Claude Code and start with:

> Read CLAUDE.md and AGENTS.md in full before doing anything else. Then read PLAN.md and TASKS.md to understand the project.
>
> Start with TASK-001 from TASKS.md. Follow the Agent Loop defined in AGENTS.md exactly: explore, plan, implement, test, run static checks, self-review, update TASKS.md — then stop and show me the diff before committing. I want to review each task before you move to the next one.
>
> Do not skip ahead to later tasks or phases. Do not touch Twilio, AWS, or Lambda code yet — Phase 1 is fetch + summarize + terminal output only.
