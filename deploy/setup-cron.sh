#!/usr/bin/env bash
set -euo pipefail

# Установка / обновление crontab для напоминаний о должниках.
#
# Использование (на сервере):
#   bash deploy/setup-cron.sh
#
# Или удалённо через ssh:
#   ssh tickets 'cd ~/spring-tickets && bash deploy/setup-cron.sh'
#
# Скрипт идемпотентен: при повторном запуске обновляет существующую запись,
# не дублируя её.

PROJECT_DIR="$HOME/spring-tickets"
VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
SCRIPT="$PROJECT_DIR/scripts/send_debtors_reminders.py"
LOG_FILE="$PROJECT_DIR/logs/debtors_reminders.log"

# Расписание: каждый день в 20:00 по Москве
SCHEDULE="0 20 * * *"
CRON_COMMENT="# tickets: debtor reminders"
CRON_LINE="$SCHEDULE TZ=Europe/Moscow $VENV_PYTHON $SCRIPT >> $LOG_FILE 2>&1"

# --- Проверки ---

if [ ! -f "$VENV_PYTHON" ]; then
    echo "ОШИБКА: Python venv не найден: $VENV_PYTHON"
    echo "Сначала выполни: python -m venv $PROJECT_DIR/.venv && pip install -r requirements.txt"
    exit 1
fi

if [ ! -f "$SCRIPT" ]; then
    echo "ОШИБКА: Скрипт не найден: $SCRIPT"
    exit 1
fi

# Создать директорию для логов
mkdir -p "$(dirname "$LOG_FILE")"

# --- Установка / обновление crontab ---

# Получить текущий crontab (или пустую строку)
CURRENT_CRONTAB=$(crontab -l 2>/dev/null || true)

if echo "$CURRENT_CRONTAB" | grep -qF "send_debtors_reminders.py"; then
    # Обновить существующую запись: удалить старую строку + комментарий, добавить новые
    NEW_CRONTAB=$(echo "$CURRENT_CRONTAB" \
        | grep -vF "send_debtors_reminders.py" \
        | grep -vF "tickets: debtor reminders")

    # Убрать лишние пустые строки в конце
    NEW_CRONTAB=$(echo "$NEW_CRONTAB" | sed -e :a -e '/^\n*$/{$d;N;ba}')

    echo "$NEW_CRONTAB
$CRON_COMMENT
$CRON_LINE" | crontab -

    echo "Crontab обновлён."
else
    # Добавить новую запись
    if [ -n "$CURRENT_CRONTAB" ]; then
        echo "$CURRENT_CRONTAB
$CRON_COMMENT
$CRON_LINE" | crontab -
    else
        echo "$CRON_COMMENT
$CRON_LINE" | crontab -
    fi

    echo "Crontab установлен."
fi

echo ""
echo "Текущий crontab:"
crontab -l
echo ""
echo "Лог: $LOG_FILE"
echo "Тест: $VENV_PYTHON $SCRIPT"
