# Data Sources

| Category | Source | API Key Needed | Free Tier Limit | Notes |
|---|---|---|---|---|
| Portfolio prices | yfinance | No | Effectively unlimited | Not an official API, scraping-based; can occasionally break |
| Global market news | Finnhub market news | Yes (free tier) | 60 req/min | Alpha Vantage can be a fallback |
| TR + global news | RSS (AA, Reuters World News) | No | Unlimited | Most stable source, no breaking-API risk |
| TR Super Lig, La Liga, PL, Serie A | API-Football | Yes (free tier) | Limited daily requests | Fine for 1 call/day |
| NBA | balldontlie.io | No | Rate-limited but fine at this volume | |
| F1 | Ergast API | No | Unlimited (archive data) | Data can lag right after a race weekend |
| Summarization | Anthropic Claude API | Yes | Usage-based, paid | Haiku model is sufficient and cheap |
| SMS delivery (Phase 2) | Twilio | Yes | Paid per SMS | Sending to Turkish numbers may require account verification |
