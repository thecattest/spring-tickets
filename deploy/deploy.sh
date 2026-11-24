#!/usr/bin/env bash
# Деплой — запускается на сервере:
#
#   bash deploy/deploy.sh
#
# git pull → сборка образа → db-backup (дамп, если есть миграции) → migrate →
# перезапуск изменившихся сервисов → ожидание healthy → чистка старых образов.
# Если что-то не поднялось (бэкап, миграция, healthcheck), скрипт завершается
# с ошибкой; уже работающие контейнеры старой версии остаются как были.
# Отката нет — чиним вперёд (docs/architecture.md → Миграции и совместимость).
#
# Первичная настройка сервера — docs/operations.md.
set -euo pipefail

cd "$(dirname "$0")/.."   # каталог проекта, откуда бы ни запустили

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
