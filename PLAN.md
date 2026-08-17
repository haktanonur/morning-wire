# PLAN.md — Architecture & Roadmap

## 1. Goal
Every morning, without manually scanning the news, get a personalized summary across 4 categories:
1. Economy and global markets
2. Personal portfolio status (today's close + change)
3. Turkey and global current events (politics/news)
4. Sports: TR Super Lig, La Liga, Premier League, Serie A, NBA, F1

**Current milestone (Phase 1):** fetch + summarize + print to the terminal. SMS delivery and cloud deployment are deliberately deferred to later phases so the core data/summarization logic can be built and reviewed first, without the added complexity of Twilio and AWS.

## 2. Out of Scope (Deliberate Decisions)
- No real-time/instant alerts — once a day
- No investment advice — data + news summary only
- No two-way interaction (you can't reply to a message to query something)
- No multi-user support
- No workflow tools like n8n — the flow is fixed and simple enough that plain code is the right level of abstraction

## 3. Overall Architecture

### Phase 1 (current)
```
CLI (python -m app.main)
        |
   +----+----+----+----+
   |         |    |    |
Portfolio  Market News Sports
fetcher    fetcher fetcher fetcher
   |         |    |    |
   +--> Claude API summarization (per-category prompt) <--+
        |
   Print to terminal, grouped by category
```
Each category runs in its own try/except block — one failing fetcher does not stop the others from printing.

### Phase 2+ (later)
```
EventBridge (cron, daily 08:00 Istanbul)
        |
AWS Lambda (lambda_handler.py -> main.py)
        |
   [same 4 fetchers + summarizer as Phase 1]
        |
   Twilio: 4 tagged SMS messages instead of terminal print
```

## 4. Category Design

### Category 1 — Economy and Global Markets
Fed/ECB statements, inflation data (PCE, NFP), major index moves, FX/commodities overview, market impact of geopolitical developments.
Source (as implemented in TASK-002): Finnhub market news only. Alpha Vantage News & Sentiment remains an unimplemented fallback option. Reuters Business RSS is no longer viable — Reuters retired its public RSS feeds.

### Category 2 — Portfolio
For each symbol in `config/portfolio.json`: closing price, % change, and any symbol-specific news.
Source: `yfinance` (price), Finnhub company news (news).

### Category 3 — Turkey and Global Current Events
Top political/economic/social headlines of the day.
Source (as implemented in TASK-003): AA RSS — Gündem and Ekonomi — for Turkey, BBC World RSS for global.
Reuters World News RSS was the original plan, but Reuters has retired its public RSS feeds and the endpoint now returns zero entries, so BBC World replaced it. GDELT is still unused; add it only if the two current sources prove too thin.

### Category 4 — Sports
TR Super Lig, La Liga, Premier League, Serie A results; NBA results; F1 race/qualifying results.
Source: API-Football (leagues), balldontlie.io (NBA, no key needed), Ergast API (F1, no key needed).
If there's nothing notable (off-season, no matches), returns "nothing notable today" instead of an empty/awkward output.

## 5. Claude API Usage
Each category gets its own prompt template in `src/app/summarizer.py`. Raw data (headlines, prices, scores) is passed to the model, which returns a concise summary. In Phase 1 there's no strict character limit (terminal output), but summaries should stay tight — 3-5 sentences per category — since Phase 2 will need to fit them into SMS segments (160 chars/segment) without a rewrite of the prompts. Model: Claude Haiku (sufficient for this, and cheap).

## 6. Phase 1 Output Format
`main.py` prints something like:
```
=== MARKETS ===
<summary>

=== PORTFOLIO ===
<summary>

=== NEWS ===
<summary>

=== SPORTS ===
<summary>
```
If a category fails, its section prints `[unavailable: <short reason>]` instead of crashing the run.

## 7. Phase 2 — SMS Delivery (Twilio)
4 categories = 4 separate Twilio calls, each prefixed with a category tag (e.g. `[MARKETS]`, `[PORTFOLIO]`). `main.py` gains a `--dry-run` flag that reuses the Phase 1 terminal-print path instead of sending. Default send order: markets → portfolio → news → sports (see open decisions in `TASKS.md`).

## 8. Phase 3+ — AWS Infrastructure
| Component | Service | Why |
|---|---|---|
| Scheduling | EventBridge (cron rule) | Free, no server to manage |
| Execution | Lambda (Python 3.12) | Free tier far exceeds daily needs |
| Secrets | Lambda environment variables | Keys never live in code |
| Logging | CloudWatch Logs | See which category failed and why |

Rationale details in `docs/adr/0003-aws-lambda-serverless.md`.

## 9. Error Handling Strategy
- Each category runs in its own try/except block
- If a data source is unreachable, that category's output becomes "data unavailable" — the rest of the run continues
- Once CloudWatch is in place (Phase 3+), failures are logged there
- A failed SMS send (Phase 2+) doesn't block the next day's run

## 10. Development Phases
Full task breakdown in `TASKS.md`. Summary:
1. Phase 0 — Skeleton (done: this file set + example `config.py`)
2. **Phase 1 — Fetch + summarize + terminal output (current focus)**
3. Phase 2 — SMS delivery (Twilio)
4. Phase 3 — Lambda orchestration wrapper
5. Phase 4 — AWS deployment (IaC, EventBridge)
6. Phase 5 — Hardening (logging, integration test, docs)

## 11. Accounts / API Keys Needed
- Anthropic API key (needed starting Phase 1)
- Finnhub or Alpha Vantage free-tier key (Phase 1)
- API-Football free-tier key (Phase 1)
- balldontlie.io, Ergast API — no key needed (Phase 1)
- Twilio account + Turkey SMS delivery approval (Phase 2)
- AWS account, free tier (Phase 3+)

## 12. Open Decisions
See the "Open Decisions" section at the end of `TASKS.md` (real portfolio symbol list, SMS send time, SMS category order for Phase 2).

## 13. Architecture Decisions (ADR)
Rationale for choosing Python, AWS Lambda, per-category SMS, etc. is recorded under `docs/adr/`.
