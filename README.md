# Daily Brief Bot

A personal daily-briefing tool. Fetches data for 4 categories — global markets, personal portfolio, TR + global news, and sports — summarizes each with the Claude API in Turkish, and sends one SMS per category through a MacroDroid webhook on the owner's own phone. A fifth category, the day's English vocabulary, is read straight off a notebook file in the repo and sent unsummarized. A GitHub Actions workflow runs the whole thing; the phone tells it when, at 06:00 Istanbul.

## Why This Exists
Some situations cut you off from the internet for a stretch of time — military
service, a hospital stay, fieldwork, a place with no coverage. The connection
goes, the browser goes, often the phone goes with them. What usually survives is
an SMS inbox.

This was built for exactly that: to keep following the handful of things you
follow every day, when the way you normally follow them is gone.

That constraint is the whole design. Every choice in this repo comes out of it:
SMS rather than an app or an email, because SMS is the channel that still
arrives; one message per category ([`docs/adr/0004`](./docs/adr/0004-per-category-sms.md)),
because a message that arrives half-read is worse than four that each stand
alone; Turkish folded into GSM-7 ([`docs/adr/0005`](./docs/adr/0005-fold-turkish-to-gsm7.md)),
because Turkish characters otherwise cut a segment from 153 characters to 67 and
the brief stops fitting; and a summarizer at all, because 160 characters of
signal beats a link to an article that cannot be opened.

It is a deliberately small window, sized to what fits on a lock screen: what the
markets did, what the portfolio did, what happened at home and outside it, how
the football went — and fifteen English words a day from a notebook, so that
time away is not time spent losing ground.

The unattended parts are unattended for the same reason. Nobody will be there to
restart a failed run, re-enter an expired key or notice a silent morning, so the
things that can quietly stop — the phone's token, the API credit — are worth
setting to outlive the deployment rather than the month. What a missing brief
means, and where to look first, is in [Part 2](#deploying-part-2-the-workflow).

## Read First
- [`CLAUDE.md`](./CLAUDE.md) / [`AGENTS.md`](./AGENTS.md) — rules every coding agent must follow in this repo, plus the Agent Loop
- [`PLAN.md`](./PLAN.md) — architecture, categories, phases
- [`TASKS.md`](./TASKS.md) — task backlog (work through this in order)
- [`docs/architecture.md`](./docs/architecture.md) — component diagram
- [`docs/data-sources.md`](./docs/data-sources.md) — APIs used and their limits

If you came here for how an AI agent was made to build this without the result
rotting, start at [How This Was Built](#how-this-was-built) instead.

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

There is no SMS provider. The brief is sent by an Android phone from its own SIM, driven by a [MacroDroid](https://www.macrodroid.com/) macro. That phone is not necessarily yours — see [When the phone belongs to someone else](#when-the-phone-belongs-to-someone-else), which is the normal case here. Twilio and NetGSM were both evaluated and rejected — see [`docs/adr/0006`](./docs/adr/0006-macrodroid-over-twilio.md), the short version being that both ask a one-person project to register as a business.

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

### When the phone belongs to someone else
The reason this project exists is also the reason the sending phone usually
cannot be the reading phone: someone with no internet cannot host the macro that
fetches the brief. So the phone above is a **relay** — a friend's Android, awake
and online, sending to a number that is not its own. Both macros go on it: this
one, and the 06:00 trigger in [Part 3](#deploying-part-3-the-clock).

Everything in Part 1 still applies, with the recipient field holding *your*
number rather than theirs. Four things change, and the first is the one that
actually breaks deployments:

- **The SMS is billed to their line.** Five categories are 7 messages a day,
  around 210 a month, every month, to a number outside their plan's own
  network. Check the bundle before anything else — a plan that runs out mid-month
  fails exactly like a dead macro, silently, and it is not a favour worth
  discovering by accident.
- **A new device means a new webhook URL.** `MACRODROID_TRIGGER_URL` in `.env`
  and in the repository secret must be re-copied from *their* phone; the old URL
  keeps answering `ok` and keeps making the wrong phone buzz.
- **Their phone must survive a reboot.** Battery optimisation is not enough on
  its own — MacroDroid also needs autostart permission, or the macros come back
  disarmed after a restart with nothing to indicate it. Test by rebooting the
  phone and then firing the `curl` above.
- **You will not be able to debug it.** Once you are offline, the arrival of the
  brief is the only signal you have, and the Actions tab and the phone are both
  out of reach. Leave them the checklist below; it is short on purpose.

**For the person holding the phone,** if a morning goes missing: is the phone on
and online, is MacroDroid still running (open it and check the macros are
enabled), and does firing the webhook macro by hand send a test SMS? Those three
cover nearly everything. If all three pass, the problem is upstream on GitHub —
usually the token having expired — and that needs the repository owner.

The token that lives on that phone is scoped to this repository with
`Actions: read and write` and nothing else, so the worst it can do in the wrong
hands is send an unwanted briefing. It cannot read or change code. That is worth
saying plainly to whoever is keeping the phone, and it is worth choosing the
longest expiry available when you create it, because nobody will be in a
position to replace it.

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

## Making This Repository Public
Nothing here has to stay private. The four API keys and the webhook URL live in
Actions secrets, which are masked in logs and are never handed to a fork; the
real `config/portfolio.json` and `.env` are gitignored and have never been
committed; and `workflow_dispatch` requires write access, so a stranger cannot
trigger the brief. The recipient's phone number is in the MacroDroid macro, not
in this repo. Publishing also makes Actions minutes free, which a private repo
bills against the monthly allowance.

Three things do become visible, and they are personal rather than secret:

- **`data/vocabulary.txt`** — the owner's own study notes, published as-is.
- **`config/portfolio.example.json`** — example symbols only, never the real
  holdings, which come from the `PORTFOLIO_JSON` secret at run time.
- **Run logs.** The workflow sends stdout to `/dev/null`, so the briefing itself
  is never written down; stderr keeps only category names, timings, character
  counts and the delivery verdict. The one exception worth knowing: a failed
  price lookup logs the *ticker* it failed on, so a bad morning can reveal which
  symbols are held — never how many, and never their value.

If any of that is unwelcome, the fix is per item — drop the notebook from the
repo, or accept the tickers — not a private repository.

## How This Was Built
Almost all of the code here was written by an AI agent (Claude Code), working to
written rules rather than to conversation. The rules are the interesting part, so
they are worth stating plainly.

**AI appears twice in this project, and the two are separate.** At runtime it is
a component: `summarizer.py` calls Claude to condense four categories into
Turkish. Its job is deliberately narrow — fetching, formatting and sending are
ordinary code, and the fifth category never touches the model at all. During
development it is the author. This section is about the second one.

**The method is spec-first: the rules exist before the code, and the agent reads
them before it writes.**

| File | Holds |
|---|---|
| [`AGENTS.md`](./AGENTS.md) | the binding rules — coding, testing, secrets, git, and the loop below |
| [`PLAN.md`](./PLAN.md) | architecture and phases |
| [`TASKS.md`](./TASKS.md) | the backlog, worked top to bottom |
| [`docs/adr/`](./docs/adr/) | decisions, with the reasoning and the rejected options |

[`CLAUDE.md`](./CLAUDE.md) only points at `AGENTS.md`. Copying the rules into
both would mean maintaining them in two places, and rules that disagree with each
other are worse than no rules.

**Every task runs the same loop:** explore → plan → implement → test → `ruff` and
`mypy` → self-review the diff → check the task off in `TASKS.md` → commit. One
task per branch, merged with `--no-ff`, and nothing starts until the last thing
finished. The result is that `git log` is the record: each task is one merge
bubble, and the commit message under it says *why*, not *what* — the diff already
says what.

**The guardrails assume the author will forget.** A human says "I won't commit a
secret"; that is a promise, not a mechanism. So:

- `tests/conftest.py` deletes every real credential and blocks outbound sockets
  before each test. A test that forgets to mock cannot quietly spend live API
  quota or fire a real SMS — it fails.
- The same file reads `config.py` with the AST module to find which secrets exist,
  so the list comes from the code rather than from someone remembering to update
  it.
- `mypy --strict`, `ruff`, 80% coverage and `detect-secrets` run in CI and in
  pre-commit, so the rules are enforced by something other than good intentions.
- Per-category error isolation is a rule, not a nicety: one dead API costs one
  `[unavailable: ...]` line, never the morning's brief.

**Claims get measured, and wrong ones get written down.** The scheduler is the
clearest example. The plan said AWS Lambda ([`0003`](./docs/adr/0003-aws-lambda-serverless.md));
it became GitHub Actions ([`0007`](./docs/adr/0007-github-actions-over-aws-lambda.md)).
That ADR then said a cron would run within about 20 minutes; two mornings of
measurement said 4.5 hours, so the cron was deleted and the phone became the
clock. Each of those reversals stayed in the repo instead of being tidied away,
because the reasoning is the part that is expensive to rediscover — and an agent
reading `TASKS.md` next month needs to know which obvious idea was already tried.

## Getting Started With Claude Code
Open this repo in Claude Code and start with:

> Read CLAUDE.md and AGENTS.md in full before doing anything else. Then read PLAN.md and TASKS.md to understand the project.
>
> Take the next unchecked task in TASKS.md. Follow the Agent Loop defined in AGENTS.md exactly: explore, plan, implement, test, run static checks, self-review, update TASKS.md — then stop and show me the diff before committing. I want to review each task before you move to the next one.
>
> Do not skip ahead to later tasks or phases. Read the ADRs under docs/adr/ before proposing anything about SMS delivery or deployment — several obvious-looking options were tried and rejected there for reasons that are not visible from the code.

The brief already runs in production, so treat a change to `sender.py`, `sms_text.py` or `daily-brief.yml` as a change to something live: the only end-to-end proof is a manual dispatch from the Actions tab after it is on `main`.
