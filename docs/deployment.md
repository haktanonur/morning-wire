# Deployment

Three parts, in order: the phone that sends the SMS, the workflow that builds the
brief, and the trigger that starts it. None of them is optional.

Examples below use **06:00** as the delivery time. It is a setting, not a
requirement — pick whatever time you want and use it consistently.

## Part 1: The Phone

Do this first — it produces `MACRODROID_TRIGGER_URL`, and nothing else can be
configured without it.

There is no SMS provider. The brief is sent by an Android phone from its own SIM,
driven by a [MacroDroid](https://www.macrodroid.com/) macro. Twilio and NetGSM
were both evaluated and rejected — see [`adr/0006`](./adr/0006-macrodroid-over-twilio.md);
the short version is that both ask a one-person project to register as a
business. That phone is not necessarily the one receiving the brief — see
[When the phone belongs to someone else](#when-the-phone-belongs-to-someone-else).

**1. Create the variable before the macro.** In MacroDroid, go to **Variables**
and add a **global string** variable named exactly `message`, lowercase. This
step is not optional and not reorderable: MacroDroid matches an incoming query
parameter to a variable *by name*, and it will not create one that does not
already exist. Get the name wrong and nothing errors — the macro runs, the relay
answers `ok`, and an empty SMS arrives.

**2. Add the macro.**

| Part | Setting |
|---|---|
| Trigger | **Connectivity → Webhook (URL)** |
| Action | **Messaging → Send SMS** |
| Recipient | the receiving number, typed into the macro |
| Message | `{v=message}` |

`{v=message}` is a variable reference; `{message}` is not the same thing and will
be sent literally. The recipient lives in the macro rather than in this repo on
purpose — `AGENTS.md` keeps real phone numbers out of the source tree.

**3. Copy the webhook URL** the trigger generates. It looks like
`https://trigger.macrodroid.com/<device-id>/<trigger-name>` and it is what goes
into `.env` and into the `MACRODROID_TRIGGER_URL` secret. **Treat it as a
password:** anyone who has it can make that phone send an SMS. It can be
regenerated from the app if it ever leaks.

**4. Let the phone act while idle.** Grant MacroDroid the SMS permission and
exclude it from battery optimisation — an aggressively dozing phone can drop the
incoming push, and the failure looks identical to a brief that was never sent.

**5. Test it by hand**, substituting your own URL:

```bash
curl "https://trigger.macrodroid.com/<device-id>/<trigger-name>?message=test"
```

The phone should buzz. Watch the phone, not the response: the endpoint is a cloud
relay that answers `ok` as soon as it has queued a push, and it answers exactly
the same way when the phone is off, out of credit, or missing the SMS permission.
That is why `sender.py` reports `accepted` and never `delivered`, and it is the
one hop no log in this project can see.

### When the phone belongs to someone else

If the person reading the brief has no internet, they cannot host the macro that
fetches it. The sending phone is then a **relay** — someone else's Android, awake
and online, sending to a number that is not its own. Both macros live on it: this
one, and the timed trigger in Part 3.

Everything above still applies, with the recipient field holding the reader's
number. Four things change:

- **The SMS is billed to their line.** Seven messages a day is roughly 210 a
  month, to a number outside their own plan. Check the bundle before anything
  else — a plan that runs out mid-month fails exactly like a dead macro, and it
  is not a favour worth discovering by accident.
- **A new device means a new webhook URL.** `MACRODROID_TRIGGER_URL` must be
  re-copied from *their* phone into both `.env` and the repository secret; the
  old URL keeps answering `ok` and keeps buzzing the wrong phone.
- **Their phone must survive a reboot.** Battery optimisation is not enough on
  its own — MacroDroid also needs autostart permission, or the macros come back
  disarmed after a restart with nothing to indicate it. Test by rebooting the
  phone and then firing the `curl` above.
- **You will not be able to debug it.** Once you are offline, the brief arriving
  is the only signal you have; the Actions tab and the phone are both out of
  reach.

**A checklist for whoever holds the phone,** if a morning goes missing: is the
phone on and online, is MacroDroid still running with its macros enabled, and
does firing the webhook macro by hand send a test SMS? Those three cover nearly
everything. If all three pass, the problem is upstream on GitHub — usually an
expired token — and needs the repository owner.

The token on that phone is scoped to this repository with `Actions: read and
write` and nothing else, so the worst it can do in the wrong hands is send an
unwanted briefing. It cannot read or change code. That is worth saying plainly to
whoever keeps the phone.

## Part 2: The Workflow

`.github/workflows/daily-brief.yml` runs the brief and is the entire deployment —
no server, no cloud functions ([`adr/0007`](./adr/0007-github-actions-over-aws-lambda.md)).

**It has no cron.** `workflow_dispatch` is its only trigger, so Part 3 is not
optional if you want a brief at all. A `schedule:` block was tried first and
removed: GitHub queues scheduled runs and drains the queue when it suits, which
delivered the brief four and a half hours late on two consecutive mornings — the
second from a cron deliberately moved 13 minutes earlier. That the start time did
not shift by even a minute is what settled it.

One trap survives from that period, because it applies to the workflow file
itself: a dispatch always runs the copy of it on **`main`**, so a change proves
nothing until it is merged.

It needs five repository secrets under **Settings → Secrets and variables →
Actions**:

| Secret | Value |
|---|---|
| `ANTHROPIC_API_KEY` | as in `.env` |
| `FINNHUB_API_KEY` | as in `.env` |
| `FOOTBALL_DATA_API_KEY` | as in `.env` |
| `MACRODROID_TRIGGER_URL` | as in `.env` — the webhook URL from Part 1 |
| `PORTFOLIO_JSON` | the **contents** of `config/portfolio.json` |

`PORTFOLIO_JSON` is the one that is easy to miss: the real portfolio file is
gitignored, so it is not in the runner's checkout and the workflow writes it back
from this secret. Without it the portfolio section reads `[unavailable: ...]`
every morning while everything else looks fine.

Run it by hand from the Actions tab — "Run workflow", with **Run the pipeline but
send no SMS** ticked for a dry run.

When a morning goes missing, the Actions tab answers the first question by
itself: **is there a run at all?** No run means the trigger never fired — a dead
token, no connectivity, or the macro disabled — and GitHub sends no failure email
in that case, because it only mails about runs that exist. A run that exists
tells you the rest from its own log.

## Part 3: The Trigger

**Required, not optional** — the workflow has no cron, so without this nothing
ever runs.

GitHub's own scheduler would not keep time here: on two consecutive mornings the
run started at the same minute, four and a half hours late, the second time from
a cron that had been moved 13 minutes earlier. Moving it changed nothing, which
is the useful measurement — the queue drains at GitHub's convenience, so no value
in `daily-brief.yml` was ever going to fix it.

**So the clock moved out of GitHub.** A `workflow_dispatch` call runs
immediately, because it is a request rather than a queued job. What issues that
call is something already awake at the delivery time and already part of this
system: the same phone that sends the SMS. It calls the GitHub API, the run
starts at once, and about a minute later the phone receives the brief it just
asked for.

The work itself cannot move to the phone — the fetching, the model calls and the
API keys all belong on the runner — so the phone's only job is to say *now*.

**1. Make a token.** GitHub → **Settings → Developer settings → Personal access
tokens → Fine-grained tokens → Generate new token**.

| Field | Value |
|---|---|
| Repository access | **Only select repositories** → this repo |
| Permissions → Repository → **Actions** | **Read and write** |
| Expiration | your choice — see the warning below |

`Actions: read and write` is the whole permission set; `Metadata: read` is added
automatically and cannot be removed. Nothing else is needed, and nothing else
should be granted: this token will live on a phone, and its blast radius should
stay at "someone could trigger a briefing". It cannot read your code or your
secrets.

Copy the token when it is shown — GitHub will not show it again.

**Expiry is a silent failure.** When the token expires the brief simply stops, and
GitHub sends no failed-run email because no run was ever started. Either set a
reminder for the expiry date or choose a long-lived token deliberately.

**2. Check the call works before involving the phone**, from your machine:

```bash
curl -i -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/<owner>/<repo>/actions/workflows/daily-brief.yml/dispatches \
  -d '{"ref":"main","inputs":{"dry_run":"true"}}'
```

**Success is `HTTP/2 204` with an empty body.** That is why `-i` is there:
without it a working call prints nothing at all and looks broken. `401` means the
token is wrong, `403` means it lacks `Actions: write`, and `404` usually means the
repo path or the workflow filename is wrong rather than that anything is missing.

`daily-brief.yml` in the URL is the filename, not the workflow's display name.
`"ref":"main"` is required — it says which branch to run, and it must be a branch
that already has this workflow on it. Note `"dry_run":"true"` is the **string**
`"true"`, not a bare `true`; the workflow compares it as text.

Then open the Actions tab. A run should be there already, and it should say
**Manually run** rather than **Scheduled**. That word is the proof: it is the
difference between the fast path and the queue.

**3. Add the macro** in MacroDroid. This is a second macro — leave the SMS one
from Part 1 alone. The settings are spread across the HTTP Request action's own
tabs:

| Tab | Field | Value |
|---|---|---|
| Settings | Request method | `POST` |
| Settings | URL | `https://api.github.com/repos/<owner>/<repo>/actions/workflows/daily-brief.yml/dispatches` |
| Settings | Block next actions until complete | **ticked**, if you want to read the status code |
| Content Body | Content type | `application/json` |
| Content Body | Body | `{"ref":"main"}` |
| Header Params | `Authorization` | `Bearer <token>` |
| Header Params | `Accept` | `application/vnd.github+json` |

The trigger is **Date/Time → Time of Day**, set to your delivery time, repeating
daily. Query Params stays empty.

Two fields that look relevant and are not. **"Use authorization" under Basic
Authorization is the wrong one** — that is HTTP Basic auth, while GitHub wants the
token in an `Authorization` *header*, which is the Header Params tab. And the body
is `{"ref":"main"}` with **no `inputs`**: `dry_run` defaults to false in the
workflow, so omitting it sends the SMS. Passing it is legal, but it is a JSON
object inside a JSON object typed on a phone keyboard, which is exactly where a
stray quote produces a `400`. If you get a `400`, retype the body by hand rather
than pasting it.

**4. Test it in three steps, not one.** Each step rules out a different thing:

1. Run the macro with MacroDroid's play/test button. Watch the **Actions tab**,
   not the phone — a new run within seconds means the token, URL and headers are
   right. It should say **Manually run**, not Scheduled.
2. Set the trigger a couple of minutes ahead and put the phone down. If the run
   appears unattended, the time trigger survives an idle screen, which is the
   part battery optimisation breaks.
3. Only then set it to the real delivery time.

To see the status code during testing, use **Settings → Save HTTP return code in
integer variable**, make it a **local** variable, and add a Display Toast action
showing it. Local variables are referenced as `{lv=name}` — `{v=name}` is the
global syntax and will appear on screen literally. Both can be deleted once it
works.

As in Part 1, **the response does not prove delivery**: `204` says GitHub accepted
the request, and the brief arriving is what says the rest of the chain worked.

**Do not add a cron back as a safety net.** It cannot tell that the phone already
triggered a run, so its only effect is a second brief every morning. A morning
when the phone is off is a morning it could not have received the SMS anyway.
