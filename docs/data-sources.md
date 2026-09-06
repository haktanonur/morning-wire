# Data Sources

| Category | Source | API Key Needed | Free Tier Limit | Notes |
|---|---|---|---|---|
| Portfolio prices | yfinance | No | Effectively unlimited | Not an official API, scraping-based; can occasionally break |
| Global market news | Finnhub market news | Yes (free tier) | 60 req/min | Alpha Vantage can be a fallback |
| TR + global news | RSS (AA Gündem, AA Ekonomi, BBC World) | No | Unlimited | Most stable source, no breaking-API risk. Reuters World News RSS was the original pick but Reuters retired its public feeds — the endpoint returns zero entries |
| PL, La Liga, Serie A | football-data.org | Yes (free tier) | 10 req/min | **TR Super Lig is not on the free tier**, so it is not covered. API-Football was the original pick but its free plan refuses the current season ("try from 2022 to 2024") |
| F1 | — | — | — | Dropped from the category by choice. It had run on Jolpica, an Ergast-compatible mirror, since the original Ergast API answers 403 |
| NBA | — | — | — | Dropped from the category: balldontlie.io started requiring an API key |
| English vocabulary | `data/vocabulary.txt`, committed to this repo | No | No API at all | The owner's own hand-written notebook. Committed rather than held as a secret, so the Actions runner gets it from the checkout and there is no extra secret to keep in step. It is appended to by hand, which is why the parser skips a malformed entry instead of raising |
| Summarization | Anthropic Claude API | Yes | Usage-based, paid | Haiku model is sufficient and cheap. **The vocabulary is never sent to it** — see `PLAN.md` §4 |
| SMS delivery (Phase 2) | MacroDroid webhook → owner's own phone | The trigger URL is itself the credential | Free; the SMS come out of the owner's mobile plan | Twilio and NetGSM were both rejected — each requires a registered sender id, and Twilio bans P2P traffic in Turkey (ADR 0006). `200 ok` means the relay queued a push, **not** that the SMS was sent |
