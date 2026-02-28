#!/usr/bin/env bash
set -euo pipefail

# Деплой на сервер: ssh tickets -> git pull -> pip install -> migrate DB -> restart
# Использование: bash deploy/deploy.sh

SSH_HOST="tickets"
REMOTE_DIR="spring-tickets"

echo "=== Деплой на $SSH_HOST ==="

ssh "$SSH_HOST" bash -s <<'REMOTE'
set -euo pipefail
cd ~/spring-tickets

echo "--- git pull ---"
git pull --ff-only

echo "--- pip install ---"
source .venv/bin/activate
pip install -q -r requirements.txt

echo "--- DB migrate ---"
python database.py

echo "--- restart services ---"
systemctl --user restart tickets-bot tickets-web

echo "--- status ---"
systemctl --user status tickets-bot tickets-web --no-pager -l

echo "=== Деплой завершён ==="
REMOTE
