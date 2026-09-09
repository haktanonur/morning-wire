# Architecture Detail

## Phase 1 Component Diagram
```
CLI (python -m app.main)
        |
        +--> fetchers/portfolio.py    --> summarizer.py --> print (Portfolio section)
        +--> fetchers/market_news.py  --> summarizer.py --> print (Markets section)
        +--> fetchers/general_news.py --> summarizer.py --> print (News section)
        +--> fetchers/sports.py       --> summarizer.py --> print (Sports section)
        +--> fetchers/vocabulary.py   -------------------> print (Vocab 1/3..3/3)
```
Each row runs in its own try/except block; `main.py` collects the results and prints them together.

The vocabulary row is short one arrow on purpose: it never reaches the
summarizer. The entries are the owner's own study notes, so there is nothing to
condense and a paraphrase would be a loss — see `PLAN.md` §4. It is also the one
row that produces several sections from a single failure boundary, so a missing
notebook costs one `[unavailable: ...]` rather than three.

## Phase 2+ Component Diagram
```
MacroDroid time trigger, 06:00 Istanbul -> POST .../dispatches (not queued)
        |
python -m app.main   (no wrapper; the CLI is the entry point)
        |
        +--> [same 4 fetcher/summarizer pairs as Phase 1, then the vocabulary file]
        |
        +--> sender.py --> sms_text.to_gsm7() --> MacroDroid webhook
                           --> owner's Android phone sends 7 tagged SMS
                               from its own SIM, in the order
                               markets -> portfolio -> news -> sports
                               -> vocab 1/3 -> 2/3 -> 3/3
```
The webhook is a relay, so the arrow out of `sender.py` stops at "queued": a
`200 ok` says nothing about whether the phone sent the message. See
`docs/adr/0006-macrodroid-over-twilio.md`.

## Module Responsibilities
| Module | Responsibility | External dependency | Phase |
|---|---|---|---|
| `config.py` | read env vars, single entry point | none | 1 |
| `fetchers/portfolio.py` | symbol price/change data | yfinance | 1 |
| `fetchers/market_news.py` | global market headlines | Finnhub | 1 |
| `fetchers/general_news.py` | TR + global news | RSS (AA Gündem/Ekonomi, BBC World) | 1 |
| `fetchers/sports.py` | football league results | football-data.org | 1 |
| `fetchers/vocabulary.py` | parse the notebook, pick the day's 15 entries, split them into messages | `data/vocabulary.txt` (in-repo, no API) | 4 |
| `summarizer.py` | turn raw data into a short Turkish summary | Anthropic Claude API | 1 |
| `sms_text.py` | fold Turkish letters into GSM-7 so a segment holds 153 chars, not 67 | none | 2 |
| `main.py` | orchestration, error isolation, terminal output, `--dry-run`, exit code | all of the above | 1–2 |
| `sender.py` | SMS delivery | MacroDroid webhook (owner's phone) | 2 |

There is no `lambda_handler.py` row any more: `docs/adr/0007` replaced Lambda with a scheduled GitHub Actions workflow, which runs `main.py` directly.

## Data Flow (Single Category, Phase 1)
1. `main.py` calls the relevant fetcher → returns raw data (dict/list)
2. Raw data goes to `summarizer.py` with a category-specific prompt
3. Claude API returns a short summary
4. `main.py` prints the summary under that category's heading
5. If any step fails, that category prints `[unavailable: <reason>]`; the others are unaffected

The vocabulary skips steps 2 and 3: `main.py` calls `daily_messages()`, which
reads the notebook, selects the day's entries by date arithmetic and renders
them, and the result goes straight to step 4 as three numbered sections.
