# BotKit LeadGen

A lead-capture bot: the enquiry is taken in chat, stored, and qualified for a manager.

[![CI](https://github.com/ninelegsdog/botkit-leadgen/actions/workflows/ci.yml/badge.svg)](https://github.com/ninelegsdog/botkit-leadgen/actions/workflows/ci.yml) [![License](https://img.shields.io/github/license/ninelegsdog/botkit-leadgen.svg)](LICENSE) [![Python](https://img.shields.io/badge/python-3.12-339933.svg)](#quick-start)

> **Status.** Runs in production on webhook transport. State: **production**.

## Contents

- [What it does](#what-it-does)
- [Features](#features)
- [Stack](#stack)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Running in production](#running-in-production)
- [Testing](#testing)
- [How this is built](#how-this-is-built)
- [Backups](#backups)
- [Development process](#development-process)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)

## What it does

Part of a family of nine production Telegram bots on Python. LeadGen is the one whose output is another team's input — a lead that is captured but never qualified is a lead nobody calls.

The testing guide is the substantial document in this repository: it documents the test markers, the offline-versus-network split, and how to run the opt-in real-Telegram E2E suite.

## Features

- **Lead questionnaire in chat** — Name, contact, service of interest and a free-text comment.
- **Qualification by follow-up question** — Budget, timeline and city — the three questions that decide whether a manager calls.
- **Leads and interaction history stored** — Every exchange is kept, so a manager opens the full context.
- **Escalation on a timeout** — `ESCALATION_MINUTES` decides when an in-progress lead stops being handled automatically.
- **In-chat admin panel** — Gated by `ADMIN_PASSWORD`; lists leads.
- **Anti-flood throttling, `/metrics`, Sentry, webhook and polling** — The operational surface every bot in this family carries.

## Stack

- Python 3.12+
- aiogram 3.x
- SQLAlchemy 2 (async) + SQLite (WAL) / PostgreSQL
- Redis
- Prometheus `/metrics`
- Sentry
- Docker, webhook (prod) / polling (dev)

## Quick start

```bash
cp .env.example .env      # fill in BOT_TOKEN and ADMIN_IDS
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
python -m src.bot
```

Requires **Python 3.12** and [`uv`](https://docs.astral.sh/uv/). Copy
`.env.example` to `.env` and fill in the bot token and admin ids before starting.

## Configuration

Every variable is declared in [`.env.example`](.env.example); nothing is read that
is not declared there.

| Variable | Required | Holds a secret |
|---|---|---|
| `ADMIN_IDS` | yes | no |
| `ADMIN_PASSWORD` | yes | yes |
| `BOT_TOKEN` | yes | yes |
| `DB_PATH` | no | no |
| `ESCALATION_MINUTES` | no | no |
| `LOG_LEVEL` | no | no |
| `METRICS_PORT` | no | no |
| `REDIS_URL` | no | no |
| `SENTRY_DSN` | no | yes |
| `WEBHOOK_SECRET` | no | yes |
| `WEBHOOK_URL` | no | no |

"Holds a secret" is classified by variable name, not by reading the value. Treat every `yes` as sensitive regardless.

Secrets never enter git: `.env` is ignored, and CI runs a gitleaks gate over the
history.

## Running in production

The bot runs behind a webhook with TLS and a health check. `deploy/` holds the
production compose file and its own `.env.example`.

```bash
cd deploy && cp .env.example .env   # fill in, then bring the stack up
```

## Testing

```bash
pytest
```

96 test functions across 18 files run offline in
CI — no Telegram account and no network. Tests that need either are marked `req`
and stay skipped unless `RUN_TELEGRAM_E2E=1` is set, so a fresh clone is green with
no secrets.

The full guide is **[README-testing.md](README-testing.md)**: test markers, the offline-versus-network split, the opt-in real-Telegram E2E suite, and the webhook secret contract.

CI also gates the lockfile (`uv lock --check`), runs gitleaks over the history,
scans the filesystem with Trivy, and validates the k6 load script.

## How this is built

```
src/
├── admin/  handlers.py
├── core/  auth.py, bot_factory.py, callbacks.py, config.py, database.py, errors.py
├── escalation/  scheduler.py
└── leadgen/  handlers.py, service.py
```

`botkit-core` is a separate published library carrying the shared runtime. This
repository depends on it by tag, not by path — see `pyproject.toml`.

## Backups

Backups and restore are a production-wide concern (systemd timers, offsite restic,
one Redis shared across bots), not a script inside a repository. The current
procedure and its caveats live in
[`botkit-monitoring/ops/backup/RESTORE.md`](https://github.com/ninelegsdog/botkit-monitoring/blob/main/ops/backup/RESTORE.md).

## Development process

This project was built in an AI-native process: the implementation was produced by
coding agents under human-led engineering control — requirement slots, constraints
and acceptance criteria defined in advance, then specification, generation, run,
check, fix.

My role in the project:

- product definition and user-facing scenarios;
- decomposition into independent engineering stages;
- context engineering: the instructions, constraints and working rules agents run under;
- management of the context window between iterations;
- the loop of specification → generation → run → verification → correction;
- validation, testing and review;
- control of repository structure, configuration, documentation and run reproducibility.

Implementation code was generated with AI coding agents under human-led engineering
control. The full description of the process, the `AGENTS.md` template, and the
review checklists for AI-written code and secrets are in
[agentic-development-playbook](https://github.com/ninelegsdog/agentic-development-playbook).

## Documentation

- **[README-testing.md](README-testing.md)** — test markers, offline vs network suites, opt-in real-Telegram E2E, webhook secret contract.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — how to set up, what CI checks, what a PR must show.
- **[SECURITY.md](SECURITY.md)** — how to report a vulnerability and what is in scope.
- **[AGENTS.md](AGENTS.md)** — the rules a coding agent working here must follow.
- **[CHANGELOG.md](CHANGELOG.md)** — what changed, and when.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: install with `uv`, run `pytest`
and `pre-commit run --all-files`, and explain why rather than what — the diff
already shows what.

## Security

Do not open a public issue for a security problem. See [SECURITY.md](SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).
