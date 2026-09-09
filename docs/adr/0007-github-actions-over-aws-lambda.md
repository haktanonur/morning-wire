# 7. Scheduled GitHub Actions Instead of AWS Lambda

## Status
Accepted. Supersedes ADR 0003, which chose AWS Lambda + EventBridge.

## Context
ADR 0003 picked Lambda for a job that runs once a day for under a minute, on the reasoning that an always-on server would be overkill. That reasoning still holds — what changed is that a *second* free scheduler turned out to already be in the project.

The repository is on GitHub and already runs a GitHub Actions workflow on every push (`.github/workflows/ci.yml`). Adding `on: schedule` to a second workflow is the entire deployment. The Lambda route, by contrast, still needs everything ADR 0003 deferred: a `lambda_handler.py` wrapper, a dependency bundle, an EventBridge rule, IAM roles, and a way to get four secrets into the function. That is four backlog tasks (TASK-009 through TASK-012) and an AWS account, against roughly twenty lines of YAML.

The packaging is the sharpest difference. This project depends on `yfinance`, `anthropic`, `feedparser` and `requests`; on Lambda those have to be zipped into a layer or a container image and rebuilt whenever a dependency moves. On Actions the install is `pip install -e ".[dev]"` — the same line CI already runs, against the same `pyproject.toml`, on the same Python 3.12.

Failure notification decides it. This is an unattended job whose only observable output is an SMS arriving on a phone; the way it fails is silently. GitHub emails the repository owner when a scheduled workflow fails, out of the box. CloudWatch does not notify anyone — it needs a metric filter, an alarm and an SNS subscription, which is more infrastructure than the job itself.

## Decision
The daily run is a GitHub Actions workflow (`.github/workflows/daily-brief.yml`, TASK-019) running `python -m app.main`, targeting 06:00 Istanbul as the EventBridge expression ADR 0003 implied. Credentials come from GitHub Actions secrets; the run log replaces CloudWatch.

**GitHub runs the job; it no longer decides when.** The workflow was scheduled with `cron` until TASK-022 removed it — the consequence below stopped being hypothetical — and its only trigger is now `workflow_dispatch`, called each morning from the owner's phone. The half of this decision about *where the code runs* is unchanged and is what the arguments above are actually about; the half about *what keeps time* did not survive contact with the queue.

AWS is dropped from the project entirely. TASK-009 (`lambda_handler.py`), TASK-010 (packaging), TASK-011 (EventBridge) and TASK-012 (Secrets Manager) are removed from `TASKS.md` rather than deferred, and `src/app/lambda_handler.py` will not be written — `main.py` is already the entry point, so the wrapper existed only to satisfy Lambda's calling convention.

## Consequences
No AWS account, no IaC, no packaging step, and one fewer place for the four secrets to live. The scheduler and CI are now the same system, running the same install on the same runner image, so a dependency that breaks the daily job breaks a CI run first.

**The schedule is best-effort, not guaranteed — and this is the cost that actually came due.** GitHub documents that "the `schedule` event can be delayed during periods of high loads of GitHub Actions workflow runs... If the load is sufficiently high enough, some queued jobs may be dropped." The top of the hour is named as a high-load window, which `0 3 * * *` sat exactly on.

This was written expecting a 06:20 rather than a 06:00. **On 2026-09-08 the first unattended run started at 07:34 UTC against a 03:00 UTC cron — 4h34m late — and the brief arrived at 10:35 Istanbul.** The run itself took 55 seconds and every message was delivered, so the pipeline was never the problem; the queue was. A brief that lands at 10:35 is not a morning brief, so the regression against EventBridge is larger than this ADR estimated. It does not reverse the decision — the packaging, secrets and failure-notification arguments above are untouched, and EventBridge would cost an AWS account to buy punctuality back — but it downgrades the schedule from "roughly 06:00" to "some time that morning".

The first mitigation was to move the cron to `"47 2 * * *"` — off the top of the hour, asking 13 minutes early. **The next morning the run started at the same minute as the day before**, 10:34 Istanbul. That is the measurement that mattered: the cron expression was not what chose the time, so no value in this file was ever going to fix it, and further tuning would have been superstition.

**The cron was therefore deleted, and the clock moved to the phone** (TASK-022). `workflow_dispatch` is now the workflow's only trigger, and a MacroDroid time trigger POSTs to the dispatch endpoint at 06:00 Istanbul. A dispatch is a request rather than a queued job, so it starts immediately — the same property that always made manual runs feel instant. GitHub still runs the job; it just no longer decides when.

The cron was removed rather than kept as a fallback: it cannot tell that the phone already triggered a run, so its only effect would be a second brief every morning, and a morning when the phone is off is a morning it could not have received the SMS anyway.

**What that costs.** A fine-grained token now lives on the phone — scoped to this repository with `Actions: read and write` and nothing else, so the worst case is an unwanted briefing. It expires, and when it does the brief stops with no error anywhere. More broadly, **the failure notification this ADR was decided on now only covers runs that started**: if the phone never calls, no run exists and GitHub mails about nothing. That is a real erosion of the argument in the Context section above, and it is accepted because the alternative was a brief at 10:34.

**A dispatch always runs the workflow file on the default branch.** The daily run therefore tracks `main` and a change to it cannot be tested from a task branch — the same constraint the cron had, for the same reason.

**GitHub disables scheduled workflows in an inactive repository** — "in a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days." This no longer applies, since there is no schedule left to disable; it is recorded here because it was one of the arguments weighed above, and because restoring a cron would restore the hazard.

**Making this repository public would leak the briefing.** Workflow run logs are visible to anyone on a public repo, and `main.py` prints the whole report — including the portfolio section — to stdout. TASK-019 discards stdout in the workflow and keeps only stderr (warnings and the delivery summary) for that reason, which also keeps the run log to the few lines worth reading.

Minutes are billable on a private repository against the account's monthly free allowance. One daily run of a minute or two is negligible beside the per-push CI runs, which are the real consumer.

ADR 0003's own trade-off — "Lambda-specific packaging needs to be learned" — is now resolved by not learning it.
