# 4. Separate SMS Per Category Instead of One Combined Message

## Status
Accepted

## Context
Fitting all 4 categories (markets, portfolio, news, sports) into a single SMS forced each one to be cut down too aggressively.

## Decision
Once SMS delivery is implemented (Phase 2), each category is sent as its own SMS with a category tag (e.g. `[PORTFOLIO]`).

## Consequences
More detailed, readable content per category. Cost roughly quadruples but the absolute number stays negligible (a few dollars/month). Four separate notifications arrive each morning instead of one; send order is defined in `PLAN.md`.

**Update:** the decision holds, but the transport is no longer Twilio — see ADR 0006. Under MacroDroid the four messages are four webhook calls instead of four API calls, and the cost argument above is moot: the messages come out of the owner's own mobile plan.
