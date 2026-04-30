#!/usr/bin/env bash
# Deploy polymarket-bond-bot on the BLAX Hetzner VPS.
#
# Auto-detects root vs non-root and chooses system- or user-mode systemd.
# Lives in its own directory (/opt/bondbot or ~/polymarket-bond-bot) — no
# collision with BLAX Flow / blax-proxy.
#
# Idempotent. Safe to re-run.
#
# One-liner from your laptop:
#   ssh -i ~/.ssh/blax_connect_vps root@204.168.195.17 \
#     'curl -fsSL https://raw.githubusercontent.com/MEHDIGAMER/polymarket-bond-bot/main/deploy/hetzner-setup.sh | bash'

set -euo pipefail

readonly REPO_URL="https://github.com/MEHDIGAMER/polymarket-bond-bot.git"
readonly SERVICE_NAME="bondbot"

if [[ $EUID -eq 0 ]]; then
  IS_ROOT=1
  BOT_HOME="/opt/bondbot"
  BOT_USER="bondbot"
  UNIT_PATH="/etc/systemd/system/$SERVICE_NAME.service"
  SYSTEMCTL=(systemctl)
else
  IS_ROOT=0
  BOT_HOME="$HOME/polymarket-bond-bot"
  BOT_USER="$(whoami)"
  UNIT_PATH="$HOME/.config/systemd/user/$SERVICE_NAME.service"
  SYSTEMCTL=(systemctl --user)
fi

echo "=========================================="
echo "  polymarket-bond-bot — deploying"
echo "  mode:  $([[ $IS_ROOT -eq 1 ]] && echo SYSTEM || echo USER)"
echo "  user:  $BOT_USER"
echo "  dir:   $BOT_HOME"
echo "=========================================="

# 1. Prereqs
for cmd in python3 git; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: $cmd not installed"; exit 1; }
done

# 2. Service user (root mode only — create dedicated low-priv user)
if [[ $IS_ROOT -eq 1 ]]; then
  if ! id -u "$BOT_USER" &>/dev/null; then
    echo "→ creating service user $BOT_USER"
    useradd --system --create-home --home-dir "$BOT_HOME" --shell /usr/sbin/nologin "$BOT_USER"
  fi
fi

# 3. Clone / pull
if [[ -d "$BOT_HOME/.git" ]]; then
  echo "→ pulling latest"
  if [[ $IS_ROOT -eq 1 ]]; then
    sudo -u "$BOT_USER" git -C "$BOT_HOME" fetch origin
    sudo -u "$BOT_USER" git -C "$BOT_HOME" reset --hard origin/main
  else
    git -C "$BOT_HOME" fetch origin
    git -C "$BOT_HOME" reset --hard origin/main
  fi
else
  echo "→ cloning $REPO_URL"
  if [[ $IS_ROOT -eq 1 ]]; then
    rm -rf "$BOT_HOME"  # was created by useradd
    git clone "$REPO_URL" "$BOT_HOME"
    chown -R "$BOT_USER:$BOT_USER" "$BOT_HOME"
  else
    git clone "$REPO_URL" "$BOT_HOME"
  fi
fi

# 4. venv
if [[ ! -d "$BOT_HOME/venv" ]]; then
  echo "→ creating venv"
  if [[ $IS_ROOT -eq 1 ]]; then
    sudo -u "$BOT_USER" python3 -m venv "$BOT_HOME/venv" || \
      apt-get install -yqq python3-venv && sudo -u "$BOT_USER" python3 -m venv "$BOT_HOME/venv"
  else
    python3 -m venv "$BOT_HOME/venv"
  fi
fi

# 5. .env (paper-trade defaults; preserve existing edits)
if [[ ! -f "$BOT_HOME/.env" ]]; then
  echo "→ writing $BOT_HOME/.env (paper-trade defaults)"
  cat > "$BOT_HOME/.env" <<'ENVEOF'
MODE=PAPER
PAPER_BANKROLL=10000
TG_BOT_TOKEN=
TG_CHAT_ID=
ENVEOF
  chmod 600 "$BOT_HOME/.env"
  if [[ $IS_ROOT -eq 1 ]]; then chown "$BOT_USER:$BOT_USER" "$BOT_HOME/.env"; fi
fi

# 6. ensure logs/data dirs exist with right ownership
mkdir -p "$BOT_HOME/logs" "$BOT_HOME/data"
if [[ $IS_ROOT -eq 1 ]]; then chown -R "$BOT_USER:$BOT_USER" "$BOT_HOME/logs" "$BOT_HOME/data"; fi

# 7. systemd unit
echo "→ writing $UNIT_PATH"
mkdir -p "$(dirname "$UNIT_PATH")"
cat > "$UNIT_PATH" <<EOF
[Unit]
Description=Polymarket Bond Bot — paper-first bond strategy trader
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
$([[ $IS_ROOT -eq 1 ]] && echo "User=$BOT_USER")
WorkingDirectory=$BOT_HOME
EnvironmentFile=$BOT_HOME/.env
ExecStart=$BOT_HOME/venv/bin/python $BOT_HOME/main.py
Restart=on-failure
RestartSec=15
StandardOutput=append:$BOT_HOME/logs/systemd.log
StandardError=append:$BOT_HOME/logs/systemd.err

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$BOT_HOME

[Install]
WantedBy=$([[ $IS_ROOT -eq 1 ]] && echo "multi-user.target" || echo "default.target")
EOF

# 8. enable + start
"${SYSTEMCTL[@]}" daemon-reload
"${SYSTEMCTL[@]}" enable "$SERVICE_NAME"
"${SYSTEMCTL[@]}" restart "$SERVICE_NAME"

# 9. health check
sleep 5
if "${SYSTEMCTL[@]}" is-active --quiet "$SERVICE_NAME"; then
  echo ""
  echo "✅ bondbot is RUNNING (mode: PAPER, virtual bankroll: \$10K)"
  echo ""
  echo "Status:    ${SYSTEMCTL[*]} status $SERVICE_NAME"
  echo "Live logs: journalctl $([[ $IS_ROOT -eq 1 ]] || echo "--user") -u $SERVICE_NAME -f"
  echo "App log:   tail -f $BOT_HOME/logs/bot.log"
  echo "DB:        sqlite3 $BOT_HOME/data/bot.db"
  echo "Stop:      ${SYSTEMCTL[*]} stop $SERVICE_NAME"
  echo "Restart:   ${SYSTEMCTL[*]} restart $SERVICE_NAME"
  echo ""
  echo "Telegram alerts: nano $BOT_HOME/.env  (then ${SYSTEMCTL[*]} restart $SERVICE_NAME)"
  echo "=========================================="
else
  echo ""
  echo "❌ bondbot failed to start. Last 30 lines:"
  journalctl $([[ $IS_ROOT -eq 1 ]] || echo "--user") -u "$SERVICE_NAME" -n 30 --no-pager 2>/dev/null \
    || tail -n 30 "$BOT_HOME/logs/systemd.err"
  exit 1
fi
