"""Daily summary report — the validation gate."""
from datetime import datetime, timedelta, timezone

from . import db


VALIDATION_TARGETS = {
    "min_resolved": 50,        # need at least 50 closed positions
    "min_win_rate": 0.94,      # 94%+ wins
    "min_avg_return": 0.045,   # 4.5%+ avg return per cycle
    "max_drawdown_24h": -0.10, # never below -10% in 24h
}


def daily_summary() -> str:
    s_total = db.stats()
    yesterday = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    s_24h = db.stats(since_iso=yesterday)
    open_count = len(db.open_positions())

    lines = [
        "═══════════════════════════════════════════════════",
        "POLYMARKET BOND BOT — daily summary",
        f"  generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "═══════════════════════════════════════════════════",
        "",
        f"OPEN positions:        {open_count}",
        "",
        "ALL-TIME (paper or live):",
        f"  resolved positions:  {s_total['resolved']}",
        f"  wins:                {s_total['wins']}",
        f"  win rate:            {s_total['win_rate']*100:.1f}%",
        f"  total P&L:           ${s_total['total_pnl']:+,.2f}",
        f"  avg return / pos:    {s_total['avg_return']*100:+.2f}%",
        "",
        "LAST 24h:",
        f"  resolved:            {s_24h['resolved']}",
        f"  wins:                {s_24h['wins']}",
        f"  win rate:            {s_24h['win_rate']*100:.1f}%",
        f"  P&L:                 ${s_24h['total_pnl']:+,.2f}",
        "",
        "VALIDATION GATES (Phase 1 → Phase 2 promotion):",
    ]

    gates = [
        ("≥50 resolved positions",
         s_total['resolved'] >= VALIDATION_TARGETS['min_resolved'],
         f"{s_total['resolved']}/50"),
        ("Win rate ≥94%",
         s_total['win_rate'] >= VALIDATION_TARGETS['min_win_rate'],
         f"{s_total['win_rate']*100:.1f}%"),
        ("Avg return ≥4.5%",
         s_total['avg_return'] >= VALIDATION_TARGETS['min_avg_return'],
         f"{s_total['avg_return']*100:+.2f}%"),
    ]
    for name, passed, value in gates:
        mark = "✅" if passed else "❌"
        lines.append(f"  {mark} {name:30s} ({value})")

    lines += ["", "═══════════════════════════════════════════════════"]
    return "\n".join(lines)


def print_skip_breakdown(limit_per_reason: int = 3) -> str:
    """What got rejected and why — useful for tuning the filter."""
    from .db import connect
    with connect() as conn:
        rows = conn.execute("""
            SELECT skip_reason, COUNT(*) AS n
            FROM skipped GROUP BY skip_reason ORDER BY n DESC LIMIT 10
        """).fetchall()
    lines = ["Top skip reasons (last run):"]
    for r in rows:
        lines.append(f"  {r['n']:4d}  {r['skip_reason']}")
    return "\n".join(lines)
