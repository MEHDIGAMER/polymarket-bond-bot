#!/usr/bin/env bash
# Deploy polymarket-bond-bot on the existing BLAX Hetzner VPS.
#
# Runs as the `blax` user (NOT root). Uses a user-mode systemd unit and
# a separate directory so it cannot touch BLAX Flow / blax-proxy / port 8000.
#
# Idempotent — safe to re-run.
#
# One-liner from your laptop:
#   ssh -i ~/.ssh/blax_connect_vps blax@204.168.195.17 \
#     'bash -s' < deploy/hetzner-setup.sh
#
# Or from the VPS shell:
#   curl -fsSL https://raw.githubusercontent.com/MEHDIGAMER/polymarket-bond-bot/main/deploy/hetzner-setup.sh | bash

set -euo pipefail

readonly BOT_HOME="$HOME/polymarket-bond-bot"
readonly REPO_URL="https://github.com/MEHDIGAMER/polymarket-bond-bot.git"
readonly SERVICE_NAME="bondbot"

echo "=========================================="
echo "  polymarket-bond-bot — user deploy"
echo "  user:  $(whoami)"
echo "  home:  $HOME"
echo "  dir:   $BOT_HOME"
echo "=========================================="

# 1. Ensure prerequisites — Python 3 + git should already be there on a BLAX VPS
for cmd in python3 git; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: $cmd not installed"; exit 1; }
done

# 2. Clone / pull
if [[ -d "$BOT_HOME/.git" ]]; then
  echo "→ pulling latest"
  git -C "$BOT_HOME" fetch origin
  git -C "$BOT_HOME" reset --hard origin/main
else
  echo "→ cloning $REPO_URL"
  git clone "$REPO_URL" "$BOT_HOME"
fi

# 3. venv (no external deps — stdlib only — but keep venv for hygiene)
if [[ ! -d "$BOT_HOME/venv" ]]; then
  echo "→ creating venv"
  python3 -m venv "$BOT_HOME/venv"
fi

# 4. .env (only created on first run; subsequent re-runs preserve user's edits)
if [[ ! -f "$BOT_HOME/.env" ]]; then
  echo "→ writing $BOT_HOME/.env (paper-trade defaults)"
  cat > "$BOT_HOME/.env" <<'ENVEOF'
MODE=PAPER
PAPER_BANKROLL=10000
TG_BOT_TOKEN=
TG_CHAT_ID=
ENVEOF
  chmod 600 "$BOT_HOME/.env"
fi

# 5. user-systemd unit — lives under ~/.config/systemd/user, no sudo needed
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/$SERVICE_NAME.service" <<EOF
[Unit]
Description=Polymarket Bond Bot — paper-first bond strategy trader
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$BOT_HOME
EnvironmentFile=$BOT_HOME/.env
ExecStart=$BOT_HOME/venv/bin/python $BOT_HOME/main.py
Restart=on-failure
RestartSec=15
StandardOutput=append:$BOT_HOME/logs/systemd.log
StandardError=append:$BOT_HOME/logs/systemd.err

[Install]
WantedBy=default.target
EOF

# 6. enable lingering so the service runs without an active login session
#    (this needs sudo once — try it, fall back to "screen" mode if denied)
if sudo -n loginctl enable-linger "$(whoami)" 2>/dev/null; then
  echo "→ user lingering enabled"
elif loginctl show-user "$(whoami)" 2>/dev/null | grep -q "Linger=yes"; then
  echo "→ user lingering already enabled"
else
  echo "⚠ could not enable lingering (no sudo). Service will only run while you have an active SSH session."
  echo "   To fix: as root, run 'loginctl enable-linger $(whoami)'"
fi

# 7. enable + start the user service
systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
systemctl --user restart "$SERVICE_NAME"

# 8. sanity check — give the bot a few seconds to spin up
sleep 5
mkdir -p "$BOT_HOME/logs"
if systemctl --user is-active --quiet "$SERVICE_NAME"; then
  echo ""
  echo "✅ bondbot is RUNNING (mode: PAPER, bankroll: \$10K virtual)"
  echo ""
  echo "Status:    systemctl --user status $SERVICE_NAME"
  echo "Live logs: journalctl --user -u $SERVICE_NAME -f"
  echo "App log:   tail -f $BOT_HOME/logs/bot.log"
  echo "DB:        sqlite3 $BOT_HOME/data/bot.db"
  echo "Stop:      systemctl --user stop $SERVICE_NAME"
  echo "Restart:   systemctl --user restart $SERVICE_NAME"
  echo ""
  echo "Edit Telegram creds: nano $BOT_HOME/.env  (then: systemctl --user restart $SERVICE_NAME)"
  echo "=========================================="
else
  echo ""
  echo "❌ bondbot failed to start. Last 30 lines:"
  journalctl --user -u "$SERVICE_NAME" -n 30 --no-pager || tail -n 30 "$BOT_HOME/logs/systemd.err" 2>/dev/null
  exit 1
fi
