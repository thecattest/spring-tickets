#!/usr/bin/env bash
set -euo pipefail

# Install systemd user services for tickets bot and web
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_DIR="$HOME/.config/systemd/user"

mkdir -p "$SERVICE_DIR"
mkdir -p "$HOME/spring-tickets/logs"

cp "$SCRIPT_DIR/tickets-bot.service" "$SERVICE_DIR/"
cp "$SCRIPT_DIR/tickets-web.service" "$SERVICE_DIR/"

systemctl --user daemon-reload
systemctl --user enable tickets-bot tickets-web

# Allow services to run without active login session
loginctl enable-linger "$USER"

echo "Installed. Usage:"
echo "  systemctl --user start tickets-bot tickets-web"
echo "  systemctl --user status tickets-bot tickets-web"
echo "  journalctl --user -u tickets-bot -f"
echo "  tail -f ~/spring-tickets/logs/bot.log"
