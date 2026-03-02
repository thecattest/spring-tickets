#!/usr/bin/env bash
set -euo pipefail

# Полная установка проекта на чистом сервере (Debian/Ubuntu).
#
# Использование:
#   1. git clone <repo> ~/spring-tickets
#   2. cd ~/spring-tickets
#   3. bash deploy/bootstrap.sh
#   4. Заполни .env секретами
#   5. bash deploy/bootstrap.sh   (повторный запуск — безопасен)
#
# Скрипт идемпотентен: можно запускать повторно.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=11
VENV_DIR="$PROJECT_DIR/.venv"
ENV_FILE="$PROJECT_DIR/.env"

# --- Цвета ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; }

# ============================================================
# 1. Системные пакеты
# ============================================================
echo ""
echo "=== 1. Системные пакеты ==="

PACKAGES=(git redis-server nginx)

MISSING=()
for pkg in "${PACKAGES[@]}"; do
    if ! dpkg -s "$pkg" &>/dev/null; then
        MISSING+=("$pkg")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    warn "Устанавливаю: ${MISSING[*]}"
    sudo apt update -qq
    sudo apt install -y "${MISSING[@]}"
else
    info "Все системные пакеты установлены"
fi

# Redis
if ! systemctl is-active --quiet redis-server; then
    sudo systemctl start redis-server
    sudo systemctl enable redis-server
    info "Redis запущен и включён"
else
    info "Redis уже работает"
fi

# ============================================================
# 2. Python 3.11+
# ============================================================
echo ""
echo "=== 2. Python ==="

# Ищем подходящий Python в системе
PYTHON_BIN=""

# Проверяем конкретные версии от новых к старым
for minor in 14 13 12 11; do
    if command -v "python3.$minor" &>/dev/null; then
        PYTHON_BIN="python3.$minor"
        break
    fi
done

# Проверяем python3
if [ -z "$PYTHON_BIN" ] && command -v python3 &>/dev/null; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.minor}')")
    if [ "$PY_VER" -ge "$PYTHON_MIN_MINOR" ]; then
        PYTHON_BIN="python3"
    fi
fi

if [ -z "$PYTHON_BIN" ]; then
    warn "Python >= 3.${PYTHON_MIN_MINOR} не найден. Устанавливаю python3.11..."

    # deadsnakes PPA для Ubuntu / Debian
    if ! grep -q deadsnakes /etc/apt/sources.list.d/* 2>/dev/null; then
        sudo apt install -y software-properties-common
        sudo add-apt-repository -y ppa:deadsnakes/ppa
        sudo apt update -qq
    fi

    sudo apt install -y python3.11 python3.11-venv python3.11-dev
    PYTHON_BIN="python3.11"
fi

PY_VERSION=$($PYTHON_BIN --version)
info "Используется: $PYTHON_BIN ($PY_VERSION)"

# Проверяем наличие venv модуля
if ! $PYTHON_BIN -m venv --help &>/dev/null; then
    warn "Устанавливаю venv для $PYTHON_BIN..."
    # Извлекаем версию для имени пакета (python3.11-venv)
    PY_PKG_VER=$($PYTHON_BIN -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    sudo apt install -y "python${PY_PKG_VER}-venv"
fi

# ============================================================
# 3. Виртуальное окружение
# ============================================================
echo ""
echo "=== 3. Виртуальное окружение ==="

if [ ! -d "$VENV_DIR" ]; then
    $PYTHON_BIN -m venv "$VENV_DIR"
    info "Venv создан: $VENV_DIR"
else
    info "Venv уже существует"
fi

source "$VENV_DIR/bin/activate"
pip install -q --upgrade pip
pip install -q -r "$PROJECT_DIR/requirements.txt"
info "Зависимости установлены"

# ============================================================
# 4. Конфигурация (.env)
# ============================================================
echo ""
echo "=== 4. Конфигурация ==="

if [ ! -f "$ENV_FILE" ]; then
    cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
    warn ".env создан из .env.example"
    echo ""
    error "ВАЖНО: заполни секреты в $ENV_FILE и запусти скрипт повторно!"
    echo "  Обязательные поля:"
    echo "    VK_BOT_TOKEN"
    echo "    VK_GROUP_ID"
    echo "    PAYMENTS_PASSWORD"
    echo ""
    exit 0
fi

# Проверяем что ключевые секреты заполнены
MISSING_SECRETS=()
for key in VK_BOT_TOKEN VK_GROUP_ID PAYMENTS_PASSWORD; do
    val=$(grep "^${key}=" "$ENV_FILE" | cut -d'=' -f2-)
    if [ -z "$val" ] || [ "$val" = "your_vk_bot_token_here" ] || [ "$val" = "your_vk_group_id_here" ]; then
        MISSING_SECRETS+=("$key")
    fi
done

if [ ${#MISSING_SECRETS[@]} -gt 0 ]; then
    error "Не заполнены секреты в .env: ${MISSING_SECRETS[*]}"
    echo "  Отредактируй $ENV_FILE и запусти скрипт повторно."
    exit 1
fi

info ".env настроен"

# ============================================================
# 5. База данных
# ============================================================
echo ""
echo "=== 5. База данных ==="

cd "$PROJECT_DIR"
$VENV_DIR/bin/python database.py
info "Схема БД создана / обновлена"

# ============================================================
# 6. Systemd + Nginx (install.sh)
# ============================================================
echo ""
echo "=== 6. Systemd + Nginx ==="

bash "$SCRIPT_DIR/install.sh"
info "Сервисы и nginx настроены"

# ============================================================
# 7. Кроны
# ============================================================
echo ""
echo "=== 7. Кроны ==="

bash "$SCRIPT_DIR/setup-cron.sh"
bash "$SCRIPT_DIR/setup-backup-cron.sh"
info "Кроны установлены"

# ============================================================
# 8. Запуск сервисов
# ============================================================
echo ""
echo "=== 8. Запуск ==="

systemctl --user restart tickets-bot tickets-web
sleep 2

BOT_STATUS=$(systemctl --user is-active tickets-bot || true)
WEB_STATUS=$(systemctl --user is-active tickets-web || true)

if [ "$BOT_STATUS" = "active" ] && [ "$WEB_STATUS" = "active" ]; then
    info "Оба сервиса запущены"
else
    warn "Статус: bot=$BOT_STATUS, web=$WEB_STATUS"
    echo "  Проверь логи:"
    echo "    journalctl --user -u tickets-bot --no-pager -n 20"
    echo "    journalctl --user -u tickets-web --no-pager -n 20"
fi

# ============================================================
# Готово
# ============================================================
echo ""
echo "=========================================="
info "Установка завершена!"
echo ""
echo "  Сайт:   http://$(hostname -I | awk '{print $1}'):80"
echo "  Логи:   tail -f $PROJECT_DIR/logs/bot.log"
echo "          tail -f $PROJECT_DIR/logs/web.log"
echo ""
echo "  SSL (после настройки DNS):"
echo "    bash $SCRIPT_DIR/setup-ssl.sh"
echo ""
