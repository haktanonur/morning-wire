# Architecture Detail

## Phase 1 Component Diagram
```
CLI (python -m app.main)
        |
        +--> fetchers/portfolio.py    --> summarizer.py --> print (Portfolio section)
        +--> fetchers/market_news.py  --> summarizer.py --> print (Markets section)
        +--> fetchers/general_news.py --> summarizer.py --> print (News section)
        +--> fetchers/sports.py       --> summarizer.py --> print (Sports section)
```
Each row runs in its own try/except block; `main.py` collects the results and prints them together.

## Phase 2+ Component Diagram
```
EventBridge (cron, daily 08:00 Istanbul)
        |
AWS Lambda (lambda_handler.py -> main.py)
        |
        +--> [same 4 fetcher/summarizer pairs as Phase 1]
        |
        +--> sender.py --> Twilio --> 4 tagged SMS messages
```

## Module Responsibilities
| Module | Responsibility | External dependency | Phase |
|---|---|---|---|
| `config.py` | read env vars, single entry point | none | 1 |
| `fetchers/portfolio.py` | symbol price/change data | yfinance | 1 |
| `fetchers/market_news.py` | global market headlines | Finnhub | 1 |
| `fetchers/general_news.py` | TR + global news | RSS (AA Gündem/Ekonomi, BBC World) | 1 |
| `fetchers/sports.py` | football league results | football-data.org | 1 |
| `summarizer.py` | turn raw data into a short Turkish summary | Anthropic Claude API | 1 |
| `sms_text.py` | fold Turkish letters into GSM-7 so a segment holds 153 chars, not 67 | none | 2 |
| `main.py` | orchestration, error isolation, terminal output (Phase 1) / dry-run CLI (Phase 2) | all of the above | 1–2 |
| `sender.py` | SMS delivery | Twilio | 2 |
| `lambda_handler.py` | wraps `main.py` for AWS Lambda | AWS Lambda runtime | 3 |

## Data Flow (Single Category, Phase 1)
1. `main.py` calls the relevant fetcher → returns raw data (dict/list)
2. Raw data goes to `summarizer.py` with a category-specific prompt
3. Claude API returns a short summary
4. `main.py` prints the summary under that category's heading
5. If any step fails, that category prints `[unavailable: <reason>]`; the others are unaffected
