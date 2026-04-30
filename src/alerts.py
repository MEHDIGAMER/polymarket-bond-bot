"""Telegram alerts. Optional — bot runs fine without if env vars unset."""
import json
import os
import urllib.request
import urllib.error
import urllib.parse


def _enabled() -> tuple[str, str] | None:
    token = os.environ.get("TG_BOT_TOKEN", "").strip()
    chat = os.environ.get("TG_CHAT_ID", "").strip()
    if not token or not chat:
        return None
    return token, chat


def send(text: str) -> bool:
    cred = _enabled()
    if not cred:
        return False
    token, chat = cred
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text[:4096],
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    try:
        with urllib.request.urlopen(url, data=body, timeout=10) as r:
            return r.status == 200
    except (urllib.error.URLError, urllib.error.HTTPError):
        return False


def fill(pos: dict) -> None:
    msg = (
        f"📥 <b>OPENED</b> {pos['side']} bond\n"
        f"<i>{pos['question'][:120]}</i>\n"
        f"price: ${pos['entry_price']:.3f}  size: ${pos['size_usd']:.2f}  "
        f"shares: {pos['shares']:.2f}\n"
        f"category: {pos['category']}"
    )
    send(msg)


def resolved(closed: dict) -> None:
    icon = "✅" if closed["status"] == "CLOSED-WIN" else (
        "🛑" if closed["status"] == "CLOSED-STOPLOSS" else "❌"
    )
    msg = (
        f"{icon} <b>{closed['status']}</b>\n"
        f"<i>{closed['question'][:120]}</i>\n"
        f"side: {closed['side']}  entry: ${closed['entry']:.3f}  "
        f"exit: ${closed['exit']:.3f}\n"
        f"P&L: <b>${closed['pnl']:+,.2f}</b>"
    )
    send(msg)


def daily_summary(text: str) -> None:
    send(f"<pre>{text}</pre>")


def error(message: str) -> None:
    send(f"⚠️ <b>BOT ERROR</b>\n{message[:1500]}")
