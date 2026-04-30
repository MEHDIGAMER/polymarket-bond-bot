"""Closes positions that have resolved. Run this every 5-15 min."""
from datetime import datetime, timezone

from .config import RISK
from . import db
from .poly_api import get_market, is_resolved


def settle_position(pos: dict, exit_price: float, status: str) -> dict:
    """Compute P&L and persist the close."""
    if status == "CLOSED-WIN":
        gross = pos["shares"] * 1.0   # YES side wins → settles at $1
        pnl = gross - pos["size_usd"]
    elif status == "CLOSED-LOSS":
        pnl = -pos["size_usd"]
    elif status == "CLOSED-STOPLOSS":
        pnl = (exit_price - pos["entry_price"]) * pos["shares"]
    else:
        pnl = 0.0

    db.close_position(
        position_id=pos["id"],
        exit_price=exit_price,
        pnl_usd=pnl,
        status=status,
    )
    return {
        "id": pos["id"],
        "question": pos["market_question"],
        "side": pos["side"],
        "entry": pos["entry_price"],
        "exit": exit_price,
        "pnl": pnl,
        "status": status,
    }


def resolve_once() -> list[dict]:
    """One sweep through all open positions. Returns list of just-closed ones."""
    just_closed: list[dict] = []

    for row in db.open_positions():
        pos = dict(row)
        market = get_market(pos["market_id"])
        if not market:
            continue

        # 1) Stop-loss check — if current price has fallen below the threshold.
        from .filters import parse_outcome_prices
        prices = parse_outcome_prices(market)
        if prices:
            yes_price, no_price = prices
            cur_price = yes_price if pos["side"] == "YES" else no_price
            if cur_price <= RISK.STOP_LOSS_PRICE:
                just_closed.append(settle_position(
                    pos, exit_price=cur_price, status="CLOSED-STOPLOSS"
                ))
                continue

        # 2) Settlement check.
        resolved, winner = is_resolved(market)
        if not resolved:
            continue
        if winner is None:
            # Resolved but ambiguous — log and stop-loss out.
            just_closed.append(settle_position(
                pos, exit_price=pos["entry_price"],
                status="CLOSED-STOPLOSS"
            ))
            continue
        status = "CLOSED-WIN" if winner == pos["side"] else "CLOSED-LOSS"
        just_closed.append(settle_position(
            pos, exit_price=1.0 if status == "CLOSED-WIN" else 0.0,
            status=status
        ))

    return just_closed
