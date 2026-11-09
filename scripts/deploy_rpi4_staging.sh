#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# botkit-leadgen — deploy на RPi4 (192.168.0.187), staging
# =============================================================================
# Использование:
#   ./scripts/deploy_rpi4_staging.sh <BOT_TOKEN> <ADMIN_IDS> [CRM_PROVIDER]
#
# Пример:
#   ./scripts/deploy_rpi4_staging.sh 123456:ABC-DEF123 987654321 generic
# =============================================================================

RPIIP="192.168.0.187"
RPIUSER="algtro"
RPIDIR="/home/algtro/botkit-leadgen-staging"

BOT_TOKEN="${1:?Укажите BOT_TOKEN (аргумент 1)}"
ADMIN_IDS="${2:?Укажите ADMIN_IDS (аргумент 2)}"
CRM_PROVIDER="${3:-generic}"

echo "=== Deploy botkit-leadgen на RPi4 ($RPIIP) ==="
echo "CRM_PROVIDER=$CRM_PROVIDER"

# 1. Сформировать .env локально из шаблона
ENV_FILE=".env.staging"
if [ ! -f "$ENV_FILE" ]; then
  echo "ОШИБКА: $ENV_FILE не найден"; exit 1
fi

sed -e "s|^BOT_TOKEN=replace-me|BOT_TOKEN=$BOT_TOKEN|" \
    -e "s|^ADMIN_IDS=replace-me|ADMIN_IDS=$ADMIN_IDS|" \
    -e "s|^CRM_PROVIDER=generic|CRM_PROVIDER=$CRM_PROVIDER|" \
    "$ENV_FILE" > "/tmp/leadgen.env.$$.staging"

echo "Локальный .env準備 OK"

# 2. Передать .env на RPi4
scp "/tmp/leadgen.env.$$.staging" "${RPIUSER}@${RPIIP}:${RPIDIR}/.env"
echo ".env передан на RPi4"

# 3. Убрать временный файл
rm -f "/tmp/leadgen.env.$$.staging"

# 4. Выполнить на RPi4: миграции + один прогон worker --once
ssh "${RPIUSER}@${RPIIP}" << 'RPIINTERACTIVE'
set -e
cd /home/algtro/botkit-leadgen-staging
source .venv/bin/activate

echo "Запуск миграций (alembic upgrade head)..."
python3 -m alembic upgrade head

echo "Один прогон CRM worker (--once)..."
python3 -m src.crm.worker --once

echo "Готово. Проверьте: python3 -m src.crm.worker --test  (ставит тестовый лид в outbox)"
RPIINTERACTIVE

echo "=== Деплой завершён ==="
