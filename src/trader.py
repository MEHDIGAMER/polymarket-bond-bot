"""Paper-trader. The live executor will share this interface."""
from datetime import datetime, timezone
from typing import Any

from .config import BOT, RISK
from . import db
from .filters import evaluate_market, kelly_size


def open_paper_position(*, market: dict, decision: str, ctx: dict[str, Any],
                        bankroll: float) -> dict | None:
    """Open a paper position. Returns the position record or None if skipped."""
    side = decision.replace("BUY-", "")  # 'YES' or 'NO'
    market_id = ctx["market_id"]

    if db.already_holding(market_id):
        db.log_skip(market_id=market_id, question=ctx["question"],
                    reason="already_holding", price=ctx["side_price"])
        return None

    # True probability assumption for bonds: matches market price (we believe the
    # market price reflects reality at >0.93). Edge = (1.0 - price). At 0.95 →
    # 5.26% edge, at 0.97 → 3.09% edge.
    edge = 1.0 - ctx["side_price"]
    odds = ctx["side_price"] / (1.0 - ctx["side_price"])
    size_usd = kelly_size(edge=edge, odds=odds, bankroll=bankroll)
    if size_usd < 10:
        db.log_skip(market_id=market_id, question=ctx["question"],
                    reason=f"position_too_small (${size_usd:.2f})",
                    price=ctx["side_price"])
        return None

    # Concentration cap on category exposure
    cat_exposure = db.category_exposure()
    cat = ctx.get("category", "uncategorized")
    cat_now = cat_exposure.get(cat, 0.0)
    if (cat_now + size_usd) / bankroll > RISK.MAX_CATEGORY_FRACTION:
        db.log_skip(market_id=market_id, question=ctx["question"],
                    reason=f"category_cap ({cat}: ${cat_now:,.0f})",
                    price=ctx["side_price"])
        return None

    # Concurrent position cap
    open_n = len(db.open_positions())
    if open_n >= RISK.MAX_CONCURRENT_POSITIONS:
        db.log_skip(market_id=market_id, question=ctx["question"],
                    reason=f"max_concurrent ({open_n})",
                    price=ctx["side_price"])
        return None

    # Shares = how many YES/NO contracts. Each settles at $1 if our side wins.
    shares = size_usd / ctx["side_price"]

    pos_id = db.insert_position(
        market_id=market_id,
        market_question=ctx["question"],
        side=side,
        entry_price=ctx["side_price"],
        size_usd=size_usd,
        shares=shares,
        end_date=ctx["end_date"],
        category=cat,
        mode=BOT.MODE,
        metadata={"decision": decision, "edge": edge, "kelly_size": size_usd},
    )
    return {
        "id": pos_id,
        "market_id": market_id,
        "question": ctx["question"],
        "side": side,
        "entry_price": ctx["side_price"],
        "size_usd": size_usd,
        "shares": shares,
        "category": cat,
    }


def trade_once(markets: list[dict], bankroll: float) -> dict[str, Any]:
    """Run one full pass: evaluate every market, open positions on candidates.

    Returns scan stats for logging + telemetry.
    """
    candidates: list[dict] = []
    opened: list[dict] = []
    skip_counts: dict[str, int] = {}

    for market in markets:
        decision, ctx = evaluate_market(market)
        if decision == "SKIP":
            reason = ctx.get("reason", "unknown")
            skip_counts[reason] = skip_counts.get(reason, 0) + 1
            continue

        candidates.append(ctx)
        if BOT.MODE == "PAPER":
            pos = open_paper_position(market=market, decision=decision,
                                      ctx=ctx, bankroll=bankroll)
            if pos:
                opened.append(pos)
        # Live mode hooks in here in Phase 2.

    bankroll_used = sum(p["size_usd"] for p in opened)
    db.log_scan(
        markets_seen=len(markets),
        candidates=len(candidates),
        opened=len(opened),
        bankroll_used=bankroll_used,
        metadata={"skip_breakdown": skip_counts, "mode": BOT.MODE},
    )
    return {
        "markets_seen": len(markets),
        "candidates": len(candidates),
        "opened": opened,
        "skip_counts": skip_counts,
    }
