# 7. Scheduled GitHub Actions Instead of AWS Lambda

## Status
Accepted. Supersedes ADR 0003, which chose AWS Lambda + EventBridge.

## Context
ADR 0003 picked Lambda for a job that runs once a day for under a minute, on the reasoning that an always-on server would be overkill. That reasoning still holds — what changed is that a *second* free scheduler turned out to already be in the project.

The repository is on GitHub and already runs a GitHub Actions workflow on every push (`.github/workflows/ci.yml`). Adding `on: schedule` to a second workflow is the entire deployment. The Lambda route, by contrast, still needs everything ADR 0003 deferred: a `lambda_handler.py` wrapper, a dependency bundle, an EventBridge rule, IAM roles, and a way to get four secrets into the function. That is four backlog tasks (TASK-009 through TASK-012) and an AWS account, against roughly twenty lines of YAML.

The packaging is the sharpest difference. This project depends on `yfinance`, `anthropic`, `feedparser` and `requests`; on Lambda those have to be zipped into a layer or a container image and rebuilt whenever a dependency moves. On Actions the install is `pip install -e ".[dev]"` — the same line CI already runs, against the same `pyproject.toml`, on the same Python 3.12.

Failure notification decides it. This is an unattended job whose only observable output is an SMS arriving on a phone; the way it fails is silently. GitHub emails the repository owner when a scheduled workflow fails, out of the box. CloudWatch does not notify anyone — it needs a metric filter, an alarm and an SNS subscription, which is more infrastructure than the job itself.

## Decision
The daily run is a scheduled GitHub Actions workflow (`.github/workflows/daily-brief.yml`, TASK-019) running `python -m app.main`, targeting 06:00 Istanbul as the EventBridge expression ADR 0003 implied. Credentials come from GitHub Actions secrets; the run log replaces CloudWatch. The cron was `"0 3 * * *"` and is now `"47 2 * * *"` — see the consequence below, which is no longer hypothetical.

AWS is dropped from the project entirely. TASK-009 (`lambda_handler.py`), TASK-010 (packaging), TASK-011 (EventBridge) and TASK-012 (Secrets Manager) are removed from `TASKS.md` rather than deferred, and `src/app/lambda_handler.py` will not be written — `main.py` is already the entry point, so the wrapper existed only to satisfy Lambda's calling convention.

## Consequences
No AWS account, no IaC, no packaging step, and one fewer place for the four secrets to live. The scheduler and CI are now the same system, running the same install on the same runner image, so a dependency that breaks the daily job breaks a CI run first.

**The schedule is best-effort, not guaranteed — and this is the cost that actually came due.** GitHub documents that "the `schedule` event can be delayed during periods of high loads of GitHub Actions workflow runs... If the load is sufficiently high enough, some queued jobs may be dropped." The top of the hour is named as a high-load window, which `0 3 * * *` sat exactly on.

This was written expecting a 06:20 rather than a 06:00. **On 2026-09-08 the first unattended run started at 07:34 UTC against a 03:00 UTC cron — 4h34m late — and the brief arrived at 10:35 Istanbul.** The run itself took 55 seconds and every message was delivered, so the pipeline was never the problem; the queue was. A brief that lands at 10:35 is not a morning brief, so the regression against EventBridge is larger than this ADR estimated. It does not reverse the decision — the packaging, secrets and failure-notification arguments above are untouched, and EventBridge would cost an AWS account to buy punctuality back — but it downgrades the schedule from "roughly 06:00" to "some time that morning".

The cron has moved to `"47 2 * * *"`: off the top of the hour, and asking 13 minutes early so a small delay lands near 06:00 instead of after it. That is a mitigation, not a fix, and it is worth being clear that no value in this file can fix a multi-hour queue. The only real fix is to stop letting GitHub choose the time — keep the workflow but start it from an always-on caller through the `workflow_dispatch` API, which is TASK-022. That trades a stored GitHub token for punctuality, which is why it was not done pre-emptively.

**Scheduled workflows only ever run on the default branch**, from its latest commit. The daily run therefore tracks `main` and cannot be tested by pushing a branch; TASK-019 adds a `workflow_dispatch` trigger so it can be run by hand.

**GitHub disables scheduled workflows in an inactive repository** — "in a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days." This repository is private, so the rule as written does not apply today, but a repo that is finished and left alone is exactly this project's expected end state. If the brief ever stops arriving with no error to show for it, check whether the workflow was disabled before debugging the code.

**Making this repository public would leak the briefing.** Workflow run logs are visible to anyone on a public repo, and `main.py` prints the whole report — including the portfolio section — to stdout. TASK-019 discards stdout in the workflow and keeps only stderr (warnings and the delivery summary) for that reason, which also keeps the run log to the few lines worth reading.

Minutes are billable on a private repository against the account's monthly free allowance. One daily run of a minute or two is negligible beside the per-push CI runs, which are the real consumer.

ADR 0003's own trade-off — "Lambda-specific packaging needs to be learned" — is now resolved by not learning it.
