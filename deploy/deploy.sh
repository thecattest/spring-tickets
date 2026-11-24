#!/usr/bin/env bash
# Деплой: запускается локально, на сервере всё делает по SSH.
#
#   bash deploy/deploy.sh
#
# На сервере: git pull → сборка образа → db-backup (дамп, если есть миграции)
# → migrate → перезапуск изменившихся сервисов → ожидание healthy → чистка
# старых образов. Если что-то не поднялось (бэкап, миграция, healthcheck),
# скрипт завершается с ошибкой; уже работающие контейнеры старой версии
# остаются как были. Отката нет — чиним вперёд (docs/architecture.md → Миграции и совместимость).
#
# Первичная настройка сервера — docs/operations.md.
set -euo pipefail

SSH_HOST="${DEPLOY_HOST:-tickets}"   # Host из ~/.ssh/config
REMOTE_DIR="${DEPLOY_DIR:-spring-tickets}"

echo "=== Деплой на $SSH_HOST:~/$REMOTE_DIR ==="

ssh "$SSH_HOST" bash -s -- "$REMOTE_DIR" <<'REMOTE'
set -euo pipefail
cd ~/"$1"

echo "--- git pull ---"
git pull --ff-only

echo "--- docker compose up ---"
# --wait: дождаться healthy у всех сервисов (разовые — успешного завершения),
# иначе ошибка. Таймаут с запасом на start_period бота (60 с) и проверки.
# --remove-orphans: убрать контейнеры сервисов, которых больше нет в compose.yaml
docker compose up -d --build --wait --wait-timeout 240 --remove-orphans

echo "--- status ---"
docker compose ps -a

echo "--- cleanup ---"
# Висячие образы от прошлых сборок; работающие и volumes не трогает
docker image prune -f

echo "=== Деплой завершён ==="
REMOTE
