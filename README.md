# Daily Brief Bot

A personal daily-briefing tool. Fetches data for 4 categories — global markets, personal portfolio, TR + global news, and sports — summarizes each with the Claude API in Turkish, and sends one SMS per category through a MacroDroid webhook on the owner's own phone. A fifth category, the day's English vocabulary, is read straight off a notebook file in the repo and sent unsummarized. A GitHub Actions workflow runs the whole thing every morning at 06:00 Istanbul.

## Read First
- [`CLAUDE.md`](./CLAUDE.md) / [`AGENTS.md`](./AGENTS.md) — rules every coding agent must follow in this repo, plus the Agent Loop
- [`PLAN.md`](./PLAN.md) — architecture, categories, phases
- [`TASKS.md`](./TASKS.md) — task backlog (work through this in order)
- [`docs/architecture.md`](./docs/architecture.md) — component diagram
- [`docs/data-sources.md`](./docs/data-sources.md) — APIs used and their limits

## Status
Phases 1–3 are done and delivering live: the brief is fetched, summarized, sent as SMS and scheduled, with no server and no AWS ([`docs/adr/0007`](./docs/adr/0007-github-actions-over-aws-lambda.md)). Scheduling is the part that did not go to plan — GitHub's cron ran hours late, so the workflow now has no schedule and the phone triggers it instead ([Part 3](#deploying-part-3-the-clock)). Phase 4 is hardening what already runs. `TASKS.md` has the exact list and the reasoning behind each item.

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
| `MACRODROID_TRIGGER_URL` | `sender.py` — the webhook URL of the SMS macro on your phone; see [Deploying, Part 1](#deploying-part-1-the-phone) | 2 |

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
Both build all 5 categories and print the result to the terminal. The first four are fetched and summarized; the fifth is the day's English vocabulary, which is read from [`data/vocabulary.txt`](./data/vocabulary.txt) and never shown to the model — the entries are the owner's own study notes, so a paraphrase would be a loss rather than a summary. Fifteen words a day go out as three numbered messages (`VOCAB 1/3`…), which makes seven SMS in total.

Each category is isolated — if one fails, the others still print, and the failure is sent as `[unavailable: ...]` rather than silently dropped. The vocabulary is one boundary for all three of its messages, so a missing notebook costs one `[unavailable: ...]` SMS rather than three identical ones.

Sending is the default because the scheduled run passes no arguments; `--dry-run` is the developer's flag, and it needs no `MACRODROID_TRIGGER_URL`. A send run exits `1` if any category failed to reach the relay — that exit code is the only failure signal the scheduled job has.

**stdout is the briefing, stderr is the run log.** They are separate because the scheduled workflow keeps only the second:

```
INFO MARKETS ok in 2.4s, 312 chars.
WARNING PORTFOLIO summary ran to 704 characters, over the 590 cap; trimming may drop its last sentence.
INFO PORTFOLIO ok in 3.1s, 590 chars.
INFO NEWS ok in 2.8s, 401 chars.
INFO SPORTS ok in 1.9s, 288 chars.
INFO VOCAB ok in 0.0s, 15 words over 3 messages.
INFO SMS relay accepted all 7 categories.
```

One line per category — which one, how long, and how long its summary came out — then one verdict line. A category that fails logs `WARNING <NAME> failed in ...` with a traceback, which is the only place the cause survives; the SMS itself says just `[unavailable: ...]`. The verdict line is logged at `ERROR` when the relay refused anything.

## Deploying, Part 1: The Phone
Do this first — it is what produces `MACRODROID_TRIGGER_URL`, and nothing else can be configured without it.

There is no SMS provider. The brief is sent by an Android phone you own, from its own SIM, driven by a [MacroDroid](https://www.macrodroid.com/) macro. Twilio and NetGSM were both evaluated and rejected — see [`docs/adr/0006`](./docs/adr/0006-macrodroid-over-twilio.md), the short version being that both ask a one-person project to register as a business.

**1. Create the variable before the macro.** In MacroDroid, go to **Variables** and add a **global string** variable named exactly `message`, lowercase. This step is not optional and not reorderable: MacroDroid matches an incoming query parameter to a variable *by name*, and it will not create one that does not already exist. Get the name wrong and nothing errors — the macro runs, the relay answers `ok`, and an empty SMS arrives.

**2. Add the macro.**

| Part | Setting |
|---|---|
| Trigger | **Connectivity → Webhook (URL)** |
| Action | **Messaging → Send SMS** |
| Recipient | your own number, typed into the macro |
| Message | `{v=message}` |

`{v=message}` is a variable reference; `{message}` is not the same thing and will be sent literally. The recipient lives in the macro rather than in this repo on purpose — `AGENTS.md` keeps real phone numbers out of the source tree.

**3. Copy the webhook URL** the trigger generates. It looks like `https://trigger.macrodroid.com/<device-id>/<trigger-name>` and it is what goes into `.env` and into the `MACRODROID_TRIGGER_URL` secret. **Treat it as a password:** anyone who has it can make your phone send an SMS. It can be regenerated from the app if it ever leaks.

**4. Let the phone act at 06:00.** Grant MacroDroid the SMS permission, and exclude it from battery optimisation — an aggressively dozing phone can drop the incoming push, and the failure looks identical to a brief that was never sent.

**5. Test it by hand**, substituting your own URL:

```bash
curl "https://trigger.macrodroid.com/<device-id>/<trigger-name>?message=test"
```

The phone should buzz. Watch the phone, not the response: the endpoint is a cloud relay that answers `ok` as soon as it has queued a push, and it answers exactly the same way when the phone is off, out of credit, or missing the SMS permission. That is why `sender.py` reports `accepted` and never `delivered`, and it is the one hop no log in this project can see.

## Deploying, Part 2: The Workflow
`.github/workflows/daily-brief.yml` runs the brief and is the entire deployment — no server, no AWS ([`docs/adr/0007`](./docs/adr/0007-github-actions-over-aws-lambda.md)).

**It has no cron.** `workflow_dispatch` is its only trigger, and the phone decides when it runs — [Part 3](#deploying-part-3-the-clock) is therefore not optional if you want a brief at all. A `schedule:` block was tried first and removed: GitHub queues scheduled runs and drains the queue when it suits, which put the brief at 10:34 Istanbul on two consecutive mornings, the second from a cron deliberately moved 13 minutes earlier. That the start time did not shift by even a minute is what settled it.

One trap survives from that period, because it applies to the workflow file itself: the dispatch always runs the copy of it on **`main`**, so a change proves nothing until it is merged.

It needs five repository secrets under **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `ANTHROPIC_API_KEY` | as in `.env` |
| `FINNHUB_API_KEY` | as in `.env` |
| `FOOTBALL_DATA_API_KEY` | as in `.env` |
| `MACRODROID_TRIGGER_URL` | as in `.env` — the webhook URL from Part 1 |
| `PORTFOLIO_JSON` | the **contents** of `config/portfolio.json` |

`PORTFOLIO_JSON` is the one that is easy to miss: the real portfolio file is gitignored, so it is not in the runner's checkout and the workflow writes it back from this secret. Without it the portfolio section reads `[unavailable: ...]` every morning while everything else looks fine.

Run it by hand from the Actions tab — "Run workflow", with **Run the pipeline but send no SMS** ticked for a dry run. Do that after merging any change to it, since the dispatch runs the copy on `main`.

When a morning goes missing, the Actions tab answers the first question by itself: **is there a run at all?** No run means the phone never asked — a dead token, no connectivity, or the macro disabled — and note that GitHub sends no failure email in this case, because it only mails about runs that exist. A run that exists tells you the rest from its own log.

## Deploying, Part 3: The Clock
**This is required, not optional** — the workflow has no cron, so without this nothing ever runs.

It is set up this way because GitHub's own scheduler would not keep time here: on both 2026-09-08 and 2026-09-09 the run started at **10:34 Istanbul**, the second time from a cron that had been moved 13 minutes earlier. Moving it changed nothing, which is the useful measurement — the queue was draining at GitHub's convenience, not ours, so no value in `daily-brief.yml` was ever going to fix it.

**So the clock moved out of GitHub.** A `workflow_dispatch` call runs immediately, because it is a request rather than a queued job. What issues that call is something already awake at 06:00 and already part of this system: the same phone that sends the SMS. It calls the GitHub API, the run starts at once, and about a minute later the phone receives the brief it just asked for.

The phone is a strange-looking scheduler but the right one here. The work itself cannot move to it — the fetching, the Claude calls and the API keys all belong on the runner — so the phone's only job is to say *now*.

**1. Make a token.** GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.

| Field | Value |
|---|---|
| Repository access | **Only select repositories** → this repo |
| Permissions → Repository → **Actions** | **Read and write** |
| Expiration | your choice — see the warning below |

`Actions: read and write` is the whole permission set; `Metadata: read` is added automatically and cannot be removed. Nothing else is needed, and nothing else should be granted: this token will live on a phone, and its blast radius should stay at "someone could trigger a briefing". It cannot read your code or your secrets.

Copy the token when it is shown — GitHub will not show it again.

**Expiry is a silent failure.** When the token expires the brief simply stops, and GitHub sends no failed-run email because no run was ever started. Either set a calendar reminder for the expiry date or choose a long-lived token deliberately.

**2. Check the call works before involving the phone**, from your machine. Substitute your token, owner and repo:

```bash
curl -i -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/<owner>/<repo>/actions/workflows/daily-brief.yml/dispatches \
  -d '{"ref":"main","inputs":{"dry_run":"true"}}'
```

**Success is `HTTP/2 204` with an empty body.** That is why `-i` is there: without it a working call prints nothing at all and looks broken. `401` means the token is wrong, `403` means it lacks `Actions: write`, and `404` usually means the repo path or the workflow filename is wrong rather than that anything is missing.

`daily-brief.yml` in the URL is the filename, not the workflow's display name. `"ref":"main"` is required — it says which branch to run, and it must be a branch that already has this workflow on it.

Note `"dry_run":"true"` is the **string** `"true"`, not a bare `true`. The workflow compares it as text.

Then open the Actions tab. A run should be there already, and it should say **Manually run** rather than **Scheduled**. That word is the proof: it is the difference between the fast path and the queue.

**3. Add the macro** in MacroDroid. This is a second macro — leave the SMS one from Part 1 alone. The settings are spread across the HTTP Request action's own tabs:

| Tab | Field | Value |
|---|---|---|
| Settings | Request method | `POST` |
| Settings | URL | `https://api.github.com/repos/<owner>/<repo>/actions/workflows/daily-brief.yml/dispatches` |
| Settings | Block next actions until complete | **ticked**, if you want to read the status code |
| Content Body | Content type | `application/json` |
| Content Body | Body | `{"ref":"main"}` |
| Header Params | `Authorization` | `Bearer <token>` |
| Header Params | `Accept` | `application/vnd.github+json` |

The trigger is **Date/Time → Time of Day**, 06:00, repeating daily. Query Params stays empty.

Two fields that look relevant and are not. **"Use authorization" under Basic Authorization is the wrong one** — that is HTTP Basic auth, while GitHub wants the token in an `Authorization` *header*, which is the Header Params tab. And the body is `{"ref":"main"}` with **no `inputs`**: `dry_run` defaults to false in the workflow, so omitting it sends the SMS. Passing it is legal but it is a JSON object inside a JSON object typed on a phone keyboard, which is exactly where a stray quote produces a `400` — and MacroDroid's editor can substitute smart quotes. If you get a `400`, retype the body by hand rather than pasting it.

**4. Test it in three steps, not one.** Each step rules out a different thing, and doing them together tells you only that something is wrong:

1. Run the macro with MacroDroid's play/test button. Watch the **Actions tab**, not the phone — a new run within seconds means the token, URL and headers are right. It should say **Manually run**, not Scheduled.
2. Set the trigger a couple of minutes ahead and put the phone down. If the run appears unattended, the time trigger survives an idle screen, which is the part battery optimisation breaks.
3. Only then set it to 06:00.

To see the status code during testing, use **Settings → Save HTTP return code in integer variable**, make it a **local** variable, and add a Display Toast action showing it. Local variables are referenced as `{lv=name}` — `{v=name}` is the global syntax and will appear on screen literally. Both the variable and the toast can be deleted once it works.

As in Part 1, **the response does not prove delivery**: `204` says GitHub accepted the request, and the brief arriving is what says the rest of the chain worked.

**Do not add a cron back as a safety net.** It cannot tell that the phone already triggered a run, so its only effect is a second brief every morning. A morning when the phone is off is a morning it could not have received the SMS anyway.

## Getting Started With Claude Code
Open this repo in Claude Code and start with:

> Read CLAUDE.md and AGENTS.md in full before doing anything else. Then read PLAN.md and TASKS.md to understand the project.
>
> Take the next unchecked task in TASKS.md. Follow the Agent Loop defined in AGENTS.md exactly: explore, plan, implement, test, run static checks, self-review, update TASKS.md — then stop and show me the diff before committing. I want to review each task before you move to the next one.
>
> Do not skip ahead to later tasks or phases. Read the ADRs under docs/adr/ before proposing anything about SMS delivery or deployment — several obvious-looking options were tried and rejected there for reasons that are not visible from the code.

The brief already runs in production, so treat a change to `sender.py`, `sms_text.py` or `daily-brief.yml` as a change to something live: the only end-to-end proof is a manual dispatch from the Actions tab after it is on `main`.
