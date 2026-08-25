# AGENTS.md — Agent Working Rules

Any coding agent (Claude Code, Cursor, Copilot Workspace, etc.) working in this repo MUST read this file before making any change. These rules are binding unless they directly conflict with an explicit instruction from the human developer in the current session.

## What This Project Is
A personal daily-briefing system. Currently in **Phase 1**: fetch data for 4 categories (global markets, personal portfolio, TR + global news, sports), summarize each with the Claude API, and print the result to the terminal. No SMS, no AWS yet — those come in later phases. See `PLAN.md` for the full roadmap and `TASKS.md` for the task backlog.

## Tech Stack
- Python 3.12+
- Anthropic Claude API (haiku model, for summarization)
- yfinance, feedparser, requests (data fetching)
- pytest + pytest-mock + responses (testing)
- ruff (lint + format), mypy (static type checking)
- pre-commit (pre-commit hooks)
- (Phase 2+) MacroDroid webhook for SMS, AWS Lambda + EventBridge for deployment

## Repository Structure
```
src/app/
  config.py            # single entry point for reading env vars
  fetchers/             # one isolated module per data source
  summarizer.py          # Claude API calls
  main.py                 # Phase 1: CLI entrypoint, prints summaries to terminal
  sender.py               # (Phase 2) SMS delivery via a MacroDroid webhook
  lambda_handler.py       # (Phase 3) wraps main.py logic for AWS Lambda
tests/                    # mirrors src/app structure 1:1
config/portfolio.example.json   # example symbol list (real list is gitignored)
docs/                      # architecture, data sources, ADRs
.github/workflows/ci.yml   # lint + type check + test pipeline
```

## Coding Rules
1. Every function must have type hints (mypy strict mode is enforced).
2. Every external API call lives in its own module under `src/app/fetchers/`, separated from business logic, so it can be mocked in tests.
3. No module reads `.env` directly; the only entry point is `src/app/config.py`.
4. **Per-category error isolation is mandatory**: if one category (e.g. the sports API) fails, the other 3 must not be affected. A failed category prints/sends "data unavailable" and the run continues.
5. Think twice before adding a new dependency; when you do, explain why in the commit message.
6. Every public function/class gets a short docstring (Google style).

## Testing Standards
- Every new module needs a matching test file under `tests/` with the same name.
- External API calls must never hit the real network in tests — mock with `pytest-mock` / `responses`.
- Minimum coverage target: 80% (enforced in CI via `--cov-fail-under=80`).
- Test naming: `test_<function>_<scenario>` (e.g. `test_fetch_portfolio_prices_handles_missing_symbol`).
- Prefer writing the test before the implementation (TDD) where practical.

## Secrets Management
- `.env` is never committed (see `.gitignore`).
- `.env.example` must always stay up to date — add new vars there whenever you add them to `config.py`.
- Never hardcode an API key or secret in code.
- Never print a full secret value in logs.
- `config/portfolio.json` (the real portfolio) is gitignored; only `config/portfolio.example.json` is tracked.

## Git & Commit Rules (Conventional Commits)
`feat:` new feature · `fix:` bug fix · `test:` add/update tests · `docs:` documentation · `chore:` deps/config · `refactor:` behavior-preserving cleanup

Example: `feat(fetchers): add yfinance-based portfolio price fetcher`

## Branch & PR Flow
1. Each task (TASK-XXX in `TASKS.md`) gets its own branch: `task/TASK-003-market-fetcher`.
2. PR description follows `.github/PULL_REQUEST_TEMPLATE.md` and references the TASK number.
3. CI (lint + type check + test) must be green before merging.
4. Self-review is mandatory before opening a PR: re-read your own diff for debug leftovers, unused imports, and rule compliance.

## Agent Loop (Development Cycle)
For every task:
1. **Explore** — pick the next open task from `TASKS.md`, read the relevant sections of `PLAN.md`/`docs/`, check for existing similar patterns in the codebase.
2. **Plan** — write a short 3–5 bullet plan for the task (this becomes the PR description draft). If something is ambiguous, ask the human developer instead of guessing.
3. **Implement** — write the code in small, single-purpose commits.
4. **Test** — write or update tests for the new/changed behavior, run `pytest` locally.
5. **Static checks** — run `ruff check .` and `mypy src`, fix everything.
6. **Self-review** — read the full diff, confirm it follows every rule in this file.
7. **Update TASKS.md** — check off the task, add notes if useful.
8. **Commit & PR** — conventional commit message, open PR, fill in the template.

Do not start the next task until the current one is fully done.

## Definition of Done
- [ ] Code written and working
- [ ] Tests written and passing, coverage target met
- [ ] `ruff` + `mypy` clean
- [ ] Docs updated if relevant
- [ ] Task checked off in `TASKS.md`
- [ ] PR opened, template filled in, CI green

## Things Not To Do
- Writing tests against real API keys (always mock)
- Letting one category's failure stop the whole run
- Expanding scope beyond what's in `TASKS.md` without checking with the human developer first
- Committing `.env`, credentials, or real phone numbers/portfolio data

## References
`PLAN.md` (architecture & phases) · `TASKS.md` (task backlog) · `docs/architecture.md` · `docs/data-sources.md` · `docs/adr/` (architecture decision records)
