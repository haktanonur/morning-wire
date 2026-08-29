# PLAN.md — Architecture & Roadmap

## 1. Goal
Every morning, without manually scanning the news, get a personalized summary across 4 categories:
1. Economy and global markets
2. Personal portfolio status (today's close + change)
3. Turkey and global current events (politics/news)
4. Sports: TR Super Lig, La Liga, Premier League, Serie A, NBA, F1 (as implemented: Premier League, La Liga, Serie A only — see §4)

**Current milestone (Phase 1):** fetch + summarize + print to the terminal. SMS delivery and cloud deployment are deliberately deferred to later phases so the core data/summarization logic can be built and reviewed first, without the added complexity of SMS delivery and AWS.

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
EventBridge (cron(0 3 * * ? *) — 06:00 Istanbul, 03:00 UTC)
        |
AWS Lambda (lambda_handler.py -> main.py)
        |
   [same 4 fetchers + summarizer as Phase 1]
        |
   MacroDroid webhook -> owner's Android phone -> 4 tagged SMS
        (markets -> portfolio -> news -> sports)
```

Türkiye dropped daylight saving in 2016 and sits on UTC+3 all year, so the cron is a fixed UTC expression with no seasonal correction.

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
Premier League, La Liga, Serie A results.
Source (as implemented in TASK-004): football-data.org.
All three originally planned sources fell through: API-Football's free plan refuses the current season, Ergast now answers 403, and balldontlie.io started requiring a key. Consequences: the **Turkish Super Lig is not covered** (not on football-data.org's free tier) and **NBA was dropped** from the category. **F1 was later dropped by choice**, so the category is football only.
Results are filtered to a recency window, so a Monday run picks up the weekend fixtures without re-reporting them all week.
If there's nothing notable (off-season, no matches), returns "nothing notable today" instead of an empty/awkward output.

## 5. Claude API Usage
Each category gets its own prompt template in `src/app/summarizer.py`. Raw data (headlines, prices, scores) is passed to the model, which returns a concise summary. Model: Claude Haiku (sufficient for this, and cheap).

**Output language is Turkish**, since the brief is delivered by SMS to a Turkish reader. The prompts themselves stay in English (see `AGENTS.md`) and just ask for Turkish output. Phase 1's terminal output is Turkish too — it shares the same summarizer.

**Length is capped at 590 characters / 2-4 sentences per category**, and the "160 chars per SMS" figure this section used to quote is wrong for this project. Turkish cannot be encoded in the GSM-7 alphabet (`ı`, `İ`, `ğ`, `Ğ`, `ş`, `Ş` and lowercase `ç` are all missing from it), so Twilio falls back to UCS-2, where a concatenated segment carries **67** characters rather than 153. `src/app/sms_text.py` folds the Turkish letters to ASCII before sending to win GSM-7 back — see `docs/adr/0005-fold-turkish-to-gsm7.md`. With the fold in place, 590 characters fits inside 4 segments: 4 × 153 = 612 units, less the 14 that the longest category tag `[PORTFOLIO] ` costs — 14 rather than 12 because the brackets are escape pairs.

Since the switch to MacroDroid (§7) those segments come out of the owner's own mobile plan rather than a Twilio bill, so the arithmetic above is about fitting the message rather than about cost. That is what made the cap affordable to raise; under Twilio it was held at 400 / 3 segments to keep the bill down.

**The cap and the length the prompts ask for are deliberately different numbers.** `_trim()` enforces the cap by cutting at a sentence boundary, so an overlong reply loses its *last* sentence — that silently removed the world half of the news summary once. The prompts carry the real budget (400 characters) and the cap sits ~1.5× above it, which covers the ~1.4× overshoot the model was measured at. Holding both at 400 was a bug: it left no headroom, so any overshoot cost a whole sentence, and a live run had 3 of 4 categories trimmed. `_trim` logs a warning whenever it fires.

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

## 7. Phase 2 — SMS Delivery (MacroDroid)
4 categories = 4 separate webhook calls, each prefixed with a category tag (e.g. `[MARKETS]`, `[PORTFOLIO]`). `main.py` gains a `--dry-run` flag that reuses the Phase 1 terminal-print path instead of sending. Send order: markets → portfolio → news → sports.

**Twilio was the original plan and was dropped**: its Turkey guidelines prohibit person-to-person traffic, which is exactly this use case, and require a registered alphanumeric sender id with corporate documents. NetGSM has the same registration problem. Instead `sender.py` calls a MacroDroid webhook and the owner's own Android phone sends the SMS from its own SIM — no registration, no per-segment bill, and no new Python dependency. See `docs/adr/0006-macrodroid-over-twilio.md` for the phone-side contract, which is not visible from this repo.

The trade is that **delivery is no longer observable**. The webhook is a cloud relay: it answers `200 ok` once it has queued a push to the phone, and answers identically when the phone is off, offline or out of credit. `SendOutcome.accepted` means the relay took it, not that the message arrived, and §9's error handling cannot cover that last hop.

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
3. Phase 2 — SMS delivery (MacroDroid webhook)
4. Phase 3 — Lambda orchestration wrapper
5. Phase 4 — AWS deployment (IaC, EventBridge)
6. Phase 5 — Hardening (logging, integration test, docs)

## 11. Accounts / API Keys Needed
- Anthropic API key (needed starting Phase 1)
- Finnhub free-tier key (Phase 1) — Alpha Vantage remains an unimplemented fallback
- football-data.org free-tier key (Phase 1)
- MacroDroid on an Android phone, with a webhook macro and its trigger URL (Phase 2) — no account approval needed, unlike the Twilio/NetGSM routes this replaced
- AWS account, free tier (Phase 3+)

## 12. Open Decisions
See the "Open Decisions" section at the end of `TASKS.md` (real portfolio symbol list, SMS send time, SMS category order for Phase 2).

## 13. Architecture Decisions (ADR)
Rationale for choosing Python, AWS Lambda, per-category SMS, etc. is recorded under `docs/adr/`.
