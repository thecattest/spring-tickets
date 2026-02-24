#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_DIR="$HOME/.config/systemd/user"

# --- Systemd user services ---
mkdir -p "$SERVICE_DIR"
mkdir -p "$HOME/spring-tickets/logs"

cp "$SCRIPT_DIR/tickets-bot.service" "$SERVICE_DIR/"
cp "$SCRIPT_DIR/tickets-web.service" "$SERVICE_DIR/"

systemctl --user daemon-reload
systemctl --user enable tickets-bot tickets-web

# Allow services to run without active login session
loginctl enable-linger "$USER"

# --- Bash aliases ---
bash "$SCRIPT_DIR/aliases.sh"

# --- Nginx ---
echo "Installing nginx config (requires sudo)..."
sudo cp "$SCRIPT_DIR/tickets-nginx.conf" /etc/nginx/sites-available/tickets
sudo ln -sf /etc/nginx/sites-available/tickets /etc/nginx/sites-enabled/tickets
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

echo ""
echo "Installed. Usage:"
echo "  systemctl --user start tickets-bot tickets-web"
echo "  systemctl --user status tickets-bot tickets-web"
echo "  journalctl --user -u tickets-bot -f"
echo "  tail -f ~/spring-tickets/logs/bot.log"
echo ""
echo "Nginx: port 80 -> uvicorn :8080"
