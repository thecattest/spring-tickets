#!/usr/bin/env bash
set -euo pipefail

# Add systemctl --user aliases to .bashrc

MARKER="# tickets-aliases"
BLOCK="$MARKER
alias start='systemctl --user start'
alias stop='systemctl --user stop'
alias restart='systemctl --user restart'
alias status='systemctl --user status'
alias enable='systemctl --user enable'
alias disable='systemctl --user disable'
alias dreload='systemctl --user daemon-reload'
alias tw-log='tail -f ~/spring-tickets/logs/web.log'
alias tb-log='tail -f ~/spring-tickets/logs/bot.log'
# end tickets-aliases"

if grep -q "$MARKER" ~/.bashrc 2>/dev/null; then
  echo "Aliases already in .bashrc, updating..."
  sed -i "/$MARKER/,/# end tickets-aliases/d" ~/.bashrc
fi

echo "$BLOCK" >> ~/.bashrc
echo "Aliases added to .bashrc. Run: source ~/.bashrc"
