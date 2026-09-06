# Daily Brief Bot

A personal daily-briefing tool. Fetches data for 4 categories — global markets, personal portfolio, TR + global news, and sports — summarizes each with the Claude API in Turkish, and sends one SMS per category through a MacroDroid webhook on the owner's own phone. The remaining phase schedules that run every morning as a GitHub Actions workflow.

## Read First
- [`CLAUDE.md`](./CLAUDE.md) / [`AGENTS.md`](./AGENTS.md) — rules every coding agent must follow in this repo, plus the Agent Loop
- [`PLAN.md`](./PLAN.md) — architecture, categories, phases
- [`TASKS.md`](./TASKS.md) — task backlog (work through this in order)
- [`docs/architecture.md`](./docs/architecture.md) — component diagram
- [`docs/data-sources.md`](./docs/data-sources.md) — APIs used and their limits

## Current Milestone: Phase 3
Phase 1 (fetch + summarize + terminal output) and Phase 2 (SMS delivery) are done, so the brief works when run by hand. Phase 3 is scheduling it: a single GitHub Actions workflow at 03:00 UTC. There is no AWS in this project — see [`docs/adr/0007`](./docs/adr/0007-github-actions-over-aws-lambda.md). `TASKS.md` has the exact task list.

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

**stdout is the briefing, stderr is the run log.** They are separate because the scheduled workflow keeps only the second:

```
INFO MARKETS ok in 2.4s, 312 chars.
WARNING PORTFOLIO summary ran to 704 characters, over the 590 cap; trimming may drop its last sentence.
INFO PORTFOLIO ok in 3.1s, 590 chars.
INFO NEWS ok in 2.8s, 401 chars.
INFO SPORTS ok in 1.9s, 288 chars.
INFO SMS relay accepted all 4 categories.
```

One line per category — which one, how long, and how long its summary came out — then one verdict line. A category that fails logs `WARNING <NAME> failed in ...` with a traceback, which is the only place the cause survives; the SMS itself says just `[unavailable: ...]`. The verdict line is logged at `ERROR` when the relay refused anything.

## The Scheduled Run
`.github/workflows/daily-brief.yml` runs the brief every day at 03:00 UTC (06:00 Istanbul) and is the entire deployment — no server, no AWS ([`docs/adr/0007`](./docs/adr/0007-github-actions-over-aws-lambda.md)).

It needs five repository secrets under **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `ANTHROPIC_API_KEY` | as in `.env` |
| `FINNHUB_API_KEY` | as in `.env` |
| `FOOTBALL_DATA_API_KEY` | as in `.env` |
| `MACRODROID_TRIGGER_URL` | as in `.env` |
| `PORTFOLIO_JSON` | the **contents** of `config/portfolio.json` |

`PORTFOLIO_JSON` is the one that is easy to miss: the real portfolio file is gitignored, so it is not in the runner's checkout and the workflow writes it back from this secret. Without it the portfolio section reads `[unavailable: ...]` every morning while everything else looks fine.

Run it by hand from the Actions tab — "Run workflow", with **Run the pipeline but send no SMS** ticked for a dry run. That is the only way to test it: scheduled workflows only ever run on the default branch, so a change to this file proves nothing until it is on `main`.

Two things to know when it misbehaves. GitHub's schedule is best-effort and can be delayed or, under load, skipped — a brief that arrives late is normal, one that never arrives is worth checking. And GitHub disables scheduled workflows in a repository with no activity for 60 days, so if the runs stop entirely, look at the Actions tab before the code.

## Getting Started With Claude Code
Open this repo in Claude Code and start with:

> Read CLAUDE.md and AGENTS.md in full before doing anything else. Then read PLAN.md and TASKS.md to understand the project.
>
> Take the next unchecked task in TASKS.md. Follow the Agent Loop defined in AGENTS.md exactly: explore, plan, implement, test, run static checks, self-review, update TASKS.md — then stop and show me the diff before committing. I want to review each task before you move to the next one.
>
> Do not skip ahead to later tasks or phases. Read the ADRs under docs/adr/ before proposing anything about SMS delivery or deployment — several obvious-looking options were tried and rejected there for reasons that are not visible from the code.
