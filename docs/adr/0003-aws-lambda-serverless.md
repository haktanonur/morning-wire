# 3. AWS Lambda Instead of a Server

## Status
Accepted

## Context
The system runs once a day for a short time. An always-on server (VPS, Raspberry Pi) would add unnecessary maintenance overhead and cost.

## Decision
AWS Lambda + EventBridge (cron) will be used once the project reaches Phase 3+. The free tier comfortably covers a once-daily invocation.

## Consequences
No server management, patching, or uptime monitoring. Trade-off: Lambda-specific packaging (dependency zip/layer) needs to be learned.
