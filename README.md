# BotKit LeadGen

Telegram-бот сбора и квалификации лидов: заявка принимается в чате, сохраняется в базе и передаётся менеджеру.

Живой бот: @LeadgenKitBot · часть портфолио из 9 Telegram-ботов на Python.

## Возможности

- Анкета лида в чате: имя, контакт, услуга, комментарий
- Квалификация по дополнительным вопросам (бюджет, сроки, город)
- Хранение лидов и истории обращений в БД
- Эскалация: автоопределение по `ESCALATION_MINUTES`
- Админка в чате: доступ по `ADMIN_PASSWORD`, список лидов
- Антифлуд-троттлинг, `/metrics`, Sentry, webhook + polling

## Стек

- Python 3.12+
- aiogram 3.x
- SQLAlchemy 2 (async) + SQLite (WAL) / PostgreSQL
- Redis
- Prometheus `/metrics`
- Sentry
- Docker, webhook (prod) / polling (dev)

## Быстрый старт

```bash
cp .env.example .env      # заполнить BOT_TOKEN и ADMIN_IDS
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
python -m src.bot
```

## Переменные окружения

ADMIN_IDS, ADMIN_PASSWORD, BOT_TOKEN, DB_PATH, ESCALATION_MINUTES, LOG_LEVEL, METRICS_PORT, REDIS_URL, SENTRY_DSN, WEBHOOK_SECRET, WEBHOOK_URL

Секреты не хранятся в git: `.env` в `.gitignore`, для переноса используется
шифрование age, в CI включён gitleaks-гейт.

## Тесты

```bash
pytest
```

88 тестов в 20 файлах.

## Бэкапы

Крон на VPS (ежедневно 04:00, retention 14 дней):

```
0 4 * * * AGE_RECIPIENT=age1... OFFSITE_TARGET=user@backup-host:/srv/backups /usr/local/bin/botkit-backup.sh <BOTNAME>
```

Восстановление:

```
botkit-restore.sh <BOTNAME> <db-name>.db ~/.secrets/keys/backup.txt [target-dir]
```

## Development process

Проект создан в AI-native процессе разработки: код производили AI coding-агенты
в настроенном мной agent harness — то есть по слотам требований, инструкций, ограничений
и критериев приёмки, которые я задал заранее.

Моя роль в проекте:

- продуктовая постановка и пользовательские сценарии;
- декомпозиция задачи на самостоятельные инженерные этапы;
- context engineering: инструкции, ограничения и рабочие правила для агентов;
- управление контекстным окном между итерациями;
- цикл «спецификация → генерация → запуск → проверка → исправление»;
- валидация результата, тестирование, ревью;
- контроль структуры репозитория, конфигурации, документации и воспроизводимости запуска.

Implementation code was generated with AI coding agents under human-led engineering control.

Полное описание процесса, шаблон `AGENTS.md` и чек-листы ревью AI-кода и секретов —
в репозитории [agentic-development-playbook](https://github.com/ninelegsdog).

## Лицензия

MIT — см. [LICENSE](LICENSE).

## Статус

Проект работает в продакшене (webhook, TLS, health-check). Состояние: **production**.
