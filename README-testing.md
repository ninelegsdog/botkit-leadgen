# Testing guide — botkit-bookingbot

Test pyramid follows `Промпт автоматизация тестирования Telegram-бота.md`.

## Levels & markers

| marker | meaning | runs on |
|--------|---------|---------|
| `no_req` | fully offline (no network/Telegram) | every commit/PR |
| `req` | needs network / real Telegram account | only with `RUN_TELEGRAM_E2E=1` |
| `unit` | isolated unit test | – |
| `integration` | local component/integration (dispatcher/FSM/webhook) | – |
| `webhook` | webhook endpoint test | – |
| `e2e` | real Telegram E2E via MTProto (Telethon) | – |
| `serial` | must not be parallelized (`-n 0`) | – |

Offline tests are auto-tagged `no_req` in `tests/conftest.py::pytest_collection_modifyitems`.
Tests marked `req` are **skipped** unless `RUN_TELEGRAM_E2E=1` is set.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# for real E2E only:
pip install -e ".[e2e]"
```

## Commands

```bash
# offline suite (parallel)
pytest -m no_req -n auto

# coverage (branch)
pytest -m no_req -n auto --cov=src --cov-branch --cov-report=term-missing --cov-report=xml

# lint
ruff check .
ruff format --check .

# single group
pytest -m "no_req and webhook" -n auto
```

## Webhook secret

`src/core/webhook.py` uses aiogram `SimpleRequestHandler(secret_token=...)` which
enforces the `X-Telegram-Bot-Api-Secret-Token` header. `tests/test_webhook.py`
asserts: valid secret → 200/202, wrong secret → 403, malformed JSON → 4xx/5xx.

## Real Telegram E2E (opt-in)

1. Create a test bot via @BotFather → `TEST_BOT_USERNAME`, `TEST_BOT_TOKEN`.
2. Create a separate Telegram **user** account for automation.
3. Get `api_id`/`api_hash` at https://my.telegram.org → API development tools.
4. `TELEGRAM_API_ID=... TELEGRAM_API_HASH=... python scripts/generate_telegram_session.py`
   → prints a `StringSession` string. Store it as `TELEGRAM_SESSION_STRING` (secret).
5. Add to `.env`:

```dotenv
TEST_BOT_USERNAME=my_test_bot
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_SESSION_STRING=
TELEGRAM_E2E_TIMEOUT=20
RUN_TELEGRAM_E2E=0
```

6. Run: `RUN_TELEGRAM_E2E=1 pytest -m "req and e2e" -n 0 -vv`

E2E waits for replies via `asyncio.Event` + `wait_for` — **no `sleep`**.
Each run uses a unique correlation token. Do not parallelize a single account.

## Secrets

Never commit tokens/hashes/session strings. `.gitignore` covers `.env`, `*.session`.
If a session string leaks, revoke the Telegram session immediately and regenerate.

## Coverage target

Current gate: `fail_under = 73` (branch). Documented target is **80%**; raise it as
more business-logic tests land.

## Known limitations

- aiogram 3.x: routing/FSM tested via `Dispatcher.feed_raw_update` + `AsyncMock`
  Bot session; `aiogram-tests` is NOT used as the sole foundation.
- `ptbtest` / original Pyrogram are intentionally avoided.
- Real E2E requires accounts/secrets you must provision; it stays skipped in CI.
