# PLAN.md — Architecture & Roadmap

## 1. Goal
Every morning, without manually scanning the news, get a personalized summary across 4 categories:
1. Economy and global markets
2. Personal portfolio status (today's close + change)
3. Turkey and global current events (politics/news)
4. Sports: TR Super Lig, La Liga, Premier League, Serie A, NBA, F1 (as implemented: Premier League, La Liga, Serie A only — see §4)

A fifth category rides along with them: the day's English vocabulary, taken from the owner's own notebook (`data/vocabulary.txt`). It is deliberately unlike the other four — nothing is fetched and nothing is summarized, because the entries are already written by the person who will read them, so the model has nothing to add and plenty it could paraphrase away. It is here rather than in a separate program because the point is that it arrives with the morning brief, at the same time, without a second thing to schedule.

**Current milestone (Phase 4):** hardening what already runs. Phase 1 (fetch + summarize + terminal output), Phase 2 (SMS delivery) and Phase 3 (the scheduled GitHub Actions run) are done, and the scheduled job has delivered live. Building the phases in that order was deliberate: the data and summarization logic was reviewed on its own before delivery or scheduling were in the way.

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
GitHub Actions schedule (cron: "47 2 * * *" — asks 05:47 Istanbul, to land near 06:00)
        |
python -m app.main   (no wrapper; the CLI is the entry point)
        |
   [same 4 fetchers + summarizer as Phase 1, then the vocabulary file]
        |
   MacroDroid webhook -> owner's Android phone -> 7 tagged SMS
        (markets -> portfolio -> news -> sports -> vocab 1/3 -> 2/3 -> 3/3)
```

Türkiye dropped daylight saving in 2016 and sits on UTC+3 all year, so the cron is a fixed UTC expression with no seasonal correction.

The scheduler was **EventBridge + Lambda** until `docs/adr/0007`: the repo already ran GitHub Actions on every push, so scheduling there costs a `on: schedule` block instead of a handler, a dependency bundle, an IAM role and an AWS account. The trade is that GitHub's schedule is best-effort — it can be delayed at the top of the hour and, under enough load, dropped — where EventBridge's was not.

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

### Category 5 — English Vocabulary
Fifteen entries a day out of `data/vocabulary.txt`, the owner's own notebook: the English term, its Turkish meaning, his note on usage, and an example sentence.
Source: a file committed to this repository. There is no API and no key. The file is data rather than configuration, which is why it is committed instead of held as a repository secret — the runner then gets it from the checkout, and there is no sixth secret to keep in step.

**No summarizer.** This is the only category the model never sees. The entries are already written, in Turkish, by the person about to read them; a "helpful" rewrite would replace study material with the model's guess at it, and there is nothing to condense. The category therefore costs no API call, and its text is the only text in the brief that is not model-generated.

**Selection is a pure function of the date**: `(date.toordinal() * 15) % len(entries)`. Nothing is stored between runs, deliberately — the scheduled job gets a fresh runner every morning, so a cursor would have to be committed back into the repo or cached, and neither is worth it for a notebook meant to be read round and round. 15 and 449 share no common factor, so the offset walks every entry before repeating; a re-run after a failed send repeats the morning's list rather than skipping past it, and the second pass over the notebook is revision rather than a defect.

**Split across three messages of five.** The SMS length itself does not matter here — the messages come off the owner's own SIM (§7) — but the message travels as a *URL query parameter* to a third-party relay with an unpublished request-line limit, and that relay answers `200 ok` whether or not the whole parameter survived. All fifteen at once is ~3,300 encoded characters with no way to notice truncation; five at a time is ~1,100, far inside anything plausible, and reads better on a phone. The entries are numbered continuously (1–15) across the three messages so the reader can see that none went missing.

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

=== VOCAB 1/3 ===
<five numbered entries>
...
```
If a category fails, its section prints `[unavailable: <short reason>]` instead of crashing the run. The vocabulary is one failure boundary for all three of its messages, so a missing notebook prints (and sends) a single `[unavailable: ...]` under the heading `VOCAB` rather than three identical ones.

## 7. Phase 2 — SMS Delivery (MacroDroid)
5 categories = 7 separate webhook calls, each prefixed with a category tag (e.g. `[MARKETS]`, `[PORTFOLIO]`, `[VOCAB 2/3]`). `main.py` gains a `--dry-run` flag that reuses the Phase 1 terminal-print path instead of sending. Send order: markets → portfolio → news → sports → vocabulary. Vocabulary goes last because it is study material rather than news — the part worth re-reading later in the day rather than at 06:00.

**Twilio was the original plan and was dropped**: its Turkey guidelines prohibit person-to-person traffic, which is exactly this use case, and require a registered alphanumeric sender id with corporate documents. NetGSM has the same registration problem. Instead `sender.py` calls a MacroDroid webhook and the owner's own Android phone sends the SMS from its own SIM — no registration, no per-segment bill, and no new Python dependency. See `docs/adr/0006-macrodroid-over-twilio.md` for the phone-side contract, which is not visible from this repo.

The trade is that **delivery is no longer observable**. The webhook is a cloud relay: it answers `200 ok` once it has queued a push to the phone, and answers identically when the phone is off, offline or out of credit. `SendOutcome.accepted` means the relay took it, not that the message arrived, and §9's error handling cannot cover that last hop.

## 8. Phase 3 — Scheduled Deployment (GitHub Actions)
| Component | Mechanism | Why |
|---|---|---|
| Scheduling | `on: schedule` in `.github/workflows/daily-brief.yml` | Already in the repo; no second platform |
| Execution | `python -m app.main` on an `ubuntu-latest` runner | Same install line CI already runs |
| Secrets | GitHub Actions secrets → environment variables | Keys never live in code |
| Logging | The workflow run log | Only stderr; stdout is discarded so the briefing is not written into it |
| Failure alert | GitHub's email on a failed scheduled run | The job fails silently otherwise; this is why the run exits non-zero |

**AWS was the plan until `docs/adr/0007-github-actions-over-aws-lambda.md` replaced it**, which supersedes `docs/adr/0003-aws-lambda-serverless.md` and deleted four backlog tasks (Lambda handler, packaging, EventBridge, Secrets Manager). No `lambda_handler.py` is needed: `main.py` is already the entry point.

Two caveats worth remembering: a scheduled workflow only ever runs on the **default branch**, so it cannot be tested from a task branch — hence the `workflow_dispatch` trigger — and GitHub disables scheduled workflows in a repository that has seen no activity for 60 days.

## 9. Error Handling Strategy
- Each category runs in its own try/except block
- If a data source is unreachable, that category's output becomes "data unavailable" — the rest of the run continues, and the SMS still goes out saying so
- Failures land in the GitHub Actions run log (Phase 3), which is why only stderr survives into it
- A failed SMS send doesn't block the other categories or the next day's run, but it does make the run exit non-zero so the scheduled job goes red and GitHub emails about it — otherwise a silent phone is indistinguishable from a quiet news day

## 10. Development Phases
Full task breakdown in `TASKS.md`. Summary:
1. Phase 0 — Skeleton (done: this file set + example `config.py`)
2. Phase 1 — Fetch + summarize + terminal output (done)
3. Phase 2 — SMS delivery via the MacroDroid webhook (done)
4. Phase 3 — Scheduled deployment: one GitHub Actions workflow (done, and delivering live)
5. **Phase 4 — Hardening (log format, integration test, docs) — current focus**

## 11. Accounts / API Keys Needed
- Anthropic API key (needed starting Phase 1)
- Finnhub free-tier key (Phase 1) — Alpha Vantage remains an unimplemented fallback
- football-data.org free-tier key (Phase 1)
- MacroDroid on an Android phone, with a webhook macro and its trigger URL (Phase 2) — no account approval needed, unlike the Twilio/NetGSM routes this replaced
- No cloud account. The GitHub account that already hosts the repo is the whole of Phase 3 (`docs/adr/0007`); the AWS free-tier account this list used to require is not needed.

## 12. Open Decisions
See the "Open Decisions" section at the end of `TASKS.md` (real portfolio symbol list, SMS send time, SMS category order for Phase 2).

## 13. Architecture Decisions (ADR)
Rationale for choosing Python, MacroDroid over Twilio, GitHub Actions over AWS Lambda, per-category SMS, etc. is recorded under `docs/adr/`. Two of them are supersessions (0006 over Twilio, 0007 over 0003) — read the superseding ADR before reopening either question.
