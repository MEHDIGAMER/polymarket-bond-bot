"""Main loop. systemd-friendly: run forever, exit non-zero on fatal errors."""
import logging
import signal
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.config import BOT
from src import db, poly_api, trader, resolver, report, alerts, api


# --- logging ---
Path(BOT.LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(BOT.LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("bond-bot")


# --- graceful shutdown ---
_RUNNING = True
def _shutdown(signum, _frame):
    global _RUNNING
    log.info(f"received signal {signum} — shutting down after current loop")
    _RUNNING = False
signal.signal(signal.SIGINT, _shutdown)
signal.signal(signal.SIGTERM, _shutdown)


def _bankroll() -> float:
    """Effective bankroll = paper bankroll - open exposure."""
    if BOT.MODE != "PAPER":
        # In live mode this would query the wallet USDC balance.
        return BOT.PAPER_BANKROLL
    open_pos = db.open_positions()
    used = sum(p["size_usd"] for p in open_pos)
    return max(0, BOT.PAPER_BANKROLL - used)


def main():
    log.info(f"starting polymarket-bond-bot mode={BOT.MODE} bankroll=${BOT.PAPER_BANKROLL:,.0f}")
    db.init_db()
    api_thread = api.serve_in_thread()
    log.info(f"API listening on 0.0.0.0:{api.API_PORT} (key in data/api.key)")
    alerts.send(f"🤖 bond-bot started ({BOT.MODE} mode, ${BOT.PAPER_BANKROLL:,.0f} bankroll, API:{api.API_PORT})")

    last_daily_report = datetime.now(timezone.utc) - timedelta(hours=24)

    loop_count = 0
    while _RUNNING:
        loop_count += 1
        try:
            log.info(f"--- loop {loop_count} ---")

            # 1) Resolve any closed markets first.
            closed = resolver.resolve_once()
            for c in closed:
                log.info(f"closed {c['status']} pnl=${c['pnl']:+,.2f} "
                         f"q={c['question'][:60]!r}")
                alerts.resolved(c)

            # 2) Scan markets and open new bonds. Paginate to pull ALL active.
            markets = poly_api.list_all_active_markets(
                max_total=BOT.MAX_MARKETS_PER_SCAN, page_size=500,
            )
            log.info(f"fetched {len(markets)} active markets")
            result = trader.trade_once(markets, bankroll=_bankroll())
            log.info(f"scan: seen={result['markets_seen']} "
                     f"candidates={result['candidates']} "
                     f"opened={len(result['opened'])} "
                     f"top_skips={sorted(result['skip_counts'].items(), key=lambda x:-x[1])[:3]}")
            for pos in result['opened']:
                alerts.fill(pos)

            # 3) Daily summary (every 24h).
            now = datetime.now(timezone.utc)
            if (now - last_daily_report).total_seconds() >= 24 * 3600:
                summary = report.daily_summary()
                log.info("\n" + summary)
                alerts.daily_summary(summary)
                last_daily_report = now

        except Exception as e:
            tb = traceback.format_exc()
            log.error(f"loop error: {e}\n{tb}")
            alerts.error(f"loop {loop_count}: {e}\n{tb[-1500:]}")

        # 4) Sleep until next scan, but respect graceful shutdown.
        for _ in range(BOT.SCAN_INTERVAL_SECONDS):
            if not _RUNNING:
                break
            time.sleep(1)

    log.info("clean shutdown — final stats:")
    log.info("\n" + report.daily_summary())
    alerts.send("🛑 bond-bot stopped")


if __name__ == "__main__":
    main()
