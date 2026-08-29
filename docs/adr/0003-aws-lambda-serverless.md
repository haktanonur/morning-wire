# 3. AWS Lambda Instead of a Server

## Status
Superseded by [ADR 0007](0007-github-actions-over-aws-lambda.md), which schedules the run with GitHub Actions instead. The premise below — that a once-daily job should not have a server under it — survived; the conclusion did not, because the repository already had a free scheduler in it.

## Context
The system runs once a day for a short time. An always-on server (VPS, Raspberry Pi) would add unnecessary maintenance overhead and cost.

## Decision
AWS Lambda + EventBridge (cron) will be used once the project reaches Phase 3+. The free tier comfortably covers a once-daily invocation.

## Consequences
No server management, patching, or uptime monitoring. Trade-off: Lambda-specific packaging (dependency zip/layer) needs to be learned.
