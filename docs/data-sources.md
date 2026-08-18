# Data Sources

| Category | Source | API Key Needed | Free Tier Limit | Notes |
|---|---|---|---|---|
| Portfolio prices | yfinance | No | Effectively unlimited | Not an official API, scraping-based; can occasionally break |
| Global market news | Finnhub market news | Yes (free tier) | 60 req/min | Alpha Vantage can be a fallback |
| TR + global news | RSS (AA Gündem, AA Ekonomi, BBC World) | No | Unlimited | Most stable source, no breaking-API risk. Reuters World News RSS was the original pick but Reuters retired its public feeds — the endpoint returns zero entries |
| PL, La Liga, Serie A | football-data.org | Yes (free tier) | 10 req/min | **TR Super Lig is not on the free tier**, so it is not covered. API-Football was the original pick but its free plan refuses the current season ("try from 2022 to 2024") |
| F1 | — | — | — | Dropped from the category by choice. It had run on Jolpica, an Ergast-compatible mirror, since the original Ergast API answers 403 |
| NBA | — | — | — | Dropped from the category: balldontlie.io started requiring an API key |
| Summarization | Anthropic Claude API | Yes | Usage-based, paid | Haiku model is sufficient and cheap |
| SMS delivery (Phase 2) | Twilio | Yes | Paid per SMS | Sending to Turkish numbers may require account verification |
