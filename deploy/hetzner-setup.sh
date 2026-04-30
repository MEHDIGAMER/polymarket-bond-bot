#!/usr/bin/env bash
# Deploy polymarket-bond-bot on the existing BLAX Flow Hetzner VPS.
# Idempotent — safe to re-run. Uses a separate user, dir, and systemd unit
# so it does NOT touch the BLAX Flow proxy infrastructure.
#
# Run once on the VPS:
#   bash <(curl -fsSL https://raw.githubusercontent.com/MEHDIGAMER/polymarket-bond-bot/main/deploy/hetzner-setup.sh)
#
# Or manually after pushing the repo:
#   ssh root@<hetzner-ip> 'bash -s' < deploy/hetzner-setup.sh

set -euo pipefail

readonly BOT_USER="bondbot"
readonly BOT_HOME="/opt/bondbot"
readonly REPO_URL="https://github.com/MEHDIGAMER/polymarket-bond-bot.git"
readonly SERVICE_NAME="bondbot"

echo "═══════════════════════════════════════════════════"
echo "  polymarket-bond-bot — Hetzner deploy"
echo "═══════════════════════════════════════════════════"

# 1. Sudo guard
if [[ $EUID -ne 0 ]]; then
  echo "must run as root (sudo)"
  exit 1
fi

# 2. System deps (Python 3.11, git)
echo "→ installing system deps"
apt-get update -qq
apt-get install -yqq python3 python3-venv python3-pip git curl

# 3. Service user (won't collide with BLAX Flow's user)
if ! id -u "$BOT_USER" &>/dev/null; then
  echo "→ creating user $BOT_USER"
  useradd --system --create-home --home-dir "$BOT_HOME" \
          --shell /bin/bash "$BOT_USER"
fi

# 4. Clone / pull repo
if [[ -d "$BOT_HOME/repo/.git" ]]; then
  echo "→ pulling latest"
  sudo -u "$BOT_USER" git -C "$BOT_HOME/repo" pull --ff-only
else
  echo "→ cloning $REPO_URL"
  sudo -u "$BOT_USER" git clone "$REPO_URL" "$BOT_HOME/repo"
fi

# 5. Python venv
if [[ ! -d "$BOT_HOME/venv" ]]; then
  echo "→ creating venv"
  sudo -u "$BOT_USER" python3 -m venv "$BOT_HOME/venv"
fi

# 6. .env file (created on first run, edit in place)
if [[ ! -f "$BOT_HOME/.env" ]]; then
  echo "→ writing $BOT_HOME/.env (paper-trade defaults)"
  cat > "$BOT_HOME/.env" <<'EOF'
# polymarket-bond-bot environment
# Paper-trade mode is the default. Don't change MODE until validation passes.
MODE=PAPER
PAPER_BANKROLL=10000

# Optional Telegram alerts. Set both to enable.
# Create a bot via @BotFather on Telegram, get chat ID via @userinfobot.
TG_BOT_TOKEN=
TG_CHAT_ID=
EOF
  chown "$BOT_USER:$BOT_USER" "$BOT_HOME/.env"
  chmod 600 "$BOT_HOME/.env"
fi

# 7. systemd unit
echo "→ writing systemd unit"
cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOF
[Unit]
Description=Polymarket Bond Bot (paper / live trader)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$BOT_USER
WorkingDirectory=$BOT_HOME/repo
EnvironmentFile=$BOT_HOME/.env
ExecStart=$BOT_HOME/venv/bin/python $BOT_HOME/repo/main.py
Restart=on-failure
RestartSec=15
StandardOutput=append:$BOT_HOME/repo/logs/systemd.log
StandardError=append:$BOT_HOME/repo/logs/systemd.err

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=$BOT_HOME

[Install]
WantedBy=multi-user.target
EOF

# 8. Enable + start
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# 9. Sanity check
sleep 3
if systemctl is-active --quiet "$SERVICE_NAME"; then
  echo ""
  echo "✅ bondbot is RUNNING"
  echo ""
  echo "Status:   systemctl status $SERVICE_NAME"
  echo "Logs:     journalctl -u $SERVICE_NAME -f"
  echo "DB:       sqlite3 $BOT_HOME/repo/data/bot.db"
  echo "Stop:     systemctl stop $SERVICE_NAME"
  echo "Restart:  systemctl restart $SERVICE_NAME"
  echo ""
  echo "Edit Telegram creds: nano $BOT_HOME/.env  (then systemctl restart $SERVICE_NAME)"
  echo "═══════════════════════════════════════════════════"
else
  echo ""
  echo "❌ bondbot failed to start. Last 30 lines:"
  journalctl -u "$SERVICE_NAME" -n 30 --no-pager
  exit 1
fi
