"""Negative-Risk Arbitrage scanner.

Finds multi-outcome events on Polymarket where buying NO on every candidate
is mathematically profitable: sum(NO_prices) < (N-1) means whoever wins,
the other (N-1) NOs each pay $1 → guaranteed profit at settlement.

Hard safety nets per debate consensus:
  • require ≥3 outcomes
  • require sum(NO) < (N-1) × (1 - fee_buffer)
  • exclude any event with "none of the above" / "other" outcome
  • exclude already-resolved or paused markets
  • cap position size per leg
"""
import json
import logging
from typing import Iterable

from .config import RISK
from . import db
from .events import emit_position_opened
from .filters import category_blacklisted


log = logging.getLogger("neg-risk")


# Question patterns that signal a "None of the above" / catch-all option.
# If ANY outcome matches these, the math breaks (the catch-all can win
# without us holding a winning leg). Skip the whole event.
NONE_OF_ABOVE_PATTERNS: tuple = (
    "none of", "other", "no one", "nobody", "neither", "not listed",
    "any other", "anyone else", "someone else",
)


def _is_catchall(outcome_text: str) -> bool:
    t = (outcome_text or "").lower().strip()
    return any(pat in t for pat in NONE_OF_ABOVE_PATTERNS)


def group_event_outcomes(markets: list[dict]) -> dict[str, list[dict]]:
    """Polymarket returns one binary YES/NO market per candidate, all linked
    by `eventId`. We cluster them back together — but ONLY for true exclusive
    multi-outcome events (Polymarket flag `negRisk: true`).

    CRITICAL: without negRisk=true, the markets under one eventId can be
    independent props (cricket: "Toss winner", "Most sixes", "Top batter")
    where ALL can resolve YES or ALL can resolve NO. Our arb math breaks.
    Only negRisk=true events guarantee "exactly one of N candidates wins."

    Also: skip any event where ANY leg fails the sports/uncertainty blacklist.
    Math holds for sports tournaments in theory, but the user wants no sports.
    """
    by_event: dict[str, list[dict]] = {}
    for m in markets:
        # Hard requirement: must be a true exclusive multi-outcome event
        if not m.get("negRisk"):
            continue
        # Apply same sports/uncertainty blacklist as bond strategy
        if category_blacklisted(m):
            continue
        eid = m.get("eventId") or m.get("event_id")
        if not eid:
            continue
        if not m.get("active") or m.get("closed"):
            continue
        by_event.setdefault(eid, []).append(m)
    return by_event


def parse_no_price(market: dict) -> float | None:
    """Extract the NO-side price for a binary market."""
    raw = market.get("outcomePrices")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, list) or len(raw) < 2:
        return None
    try:
        return float(raw[1])  # NO is index 1 in Polymarket convention
    except (ValueError, TypeError):
        return None


def evaluate_event(event_id: str, markets: list[dict]) -> dict | None:
    """Return arb opportunity dict if math holds, else None.

    Math: cost = sum(NO_i). At settlement, exactly one outcome wins → that
    one NO pays 0, the other (N-1) NOs pay $1 each → revenue = N - 1.
    Profit per $1 invested = (N - 1 - cost) / cost.
    """
    if len(markets) < RISK.NEG_RISK_MIN_OUTCOMES:
        return None

    # Skip if any outcome looks like a catchall — math breaks
    for m in markets:
        q = (m.get("question") or "") + " " + (m.get("groupItemTitle") or "")
        if _is_catchall(q):
            return None

    no_prices = []
    for m in markets:
        p = parse_no_price(m)
        if p is None or p <= 0 or p >= 1:
            return None
        # SAFETY NET 1: skip dead/stale markets where prices collapsed to ~0
        # or rocketed to ~1 (means already resolved or paused).
        if p < 0.05 or p > 0.98:
            return None
        no_prices.append((m, p))

    # Cap event size — N=35 weather markets are valid math but expensive
    # to deploy across; skip for now and revisit when bankroll grows.
    n = len(no_prices)
    if n > 12:
        return None

    sum_no = sum(p for _, p in no_prices)
    threshold = (n - 1) * (1 - RISK.NEG_RISK_FEE_BUFFER)

    if sum_no >= threshold:
        return None  # No edge

    # SAFETY NET 2: cap edge at 50%. Real arb is rarely above 30%; anything
    # above 50% signals stale/dead market that won't actually settle as expected.
    revenue_at_settlement = n - 1  # in dollars per 1 share each leg
    cost = sum_no
    edge = (revenue_at_settlement - cost) / cost
    if edge > 0.50:
        return None

    return {
        "event_id": event_id,
        "n_outcomes": n,
        "sum_no": sum_no,
        "threshold": threshold,
        "edge_pct": edge,
        "legs": no_prices,
        "guaranteed_profit_usd": (revenue_at_settlement - cost),  # per $1/leg
    }


def open_neg_risk_position(opp: dict, bankroll: float) -> list[dict]:
    """Open NO positions on every leg of a confirmed arb. Returns opened pos list."""
    leg_size = min(RISK.NEG_RISK_POSITION_USD, bankroll / (opp["n_outcomes"] * 4))
    if leg_size < 5:
        return []  # too small to bother

    opened: list[dict] = []
    for market, no_price in opp["legs"]:
        market_id = market.get("id") or market.get("conditionId")
        if not market_id or db.already_holding(market_id):
            continue

        question = (market.get("question") or "")[:120]
        shares = leg_size / no_price
        pos_id = db.insert_position(
            market_id=market_id,
            market_question=question,
            side="NO",
            entry_price=no_price,
            size_usd=leg_size,
            shares=shares,
            end_date=market.get("endDate") or "",
            category=f"NEG-RISK:{opp['event_id'][:30]}",
            mode="PAPER",
            metadata={
                "strategy": "neg_risk",
                "event_id": opp["event_id"],
                "event_n": opp["n_outcomes"],
                "edge_pct": opp["edge_pct"],
                "sum_no": opp["sum_no"],
            },
        )
        pos = {
            "id": pos_id,
            "market_id": market_id,
            "question": question,
            "side": "NO",
            "entry_price": no_price,
            "size_usd": leg_size,
            "shares": shares,
            "category": f"NEG-RISK:{opp['event_id'][:30]}",
        }
        opened.append(pos)
        emit_position_opened(pos)

    return opened


def scan(markets: list[dict], bankroll: float) -> dict:
    """Run one full negative-risk-arb scan over the market list."""
    if not markets:
        return {"events_seen": 0, "opportunities": 0, "opened": []}

    by_event = group_event_outcomes(markets)
    opportunities: list[dict] = []
    opened_total: list[dict] = []

    for eid, mkts in by_event.items():
        opp = evaluate_event(eid, mkts)
        if not opp:
            continue
        opportunities.append(opp)
        log.info(
            f"NEG-RISK opp: event={eid[:30]} n={opp['n_outcomes']} "
            f"sumNO={opp['sum_no']:.3f} edge={opp['edge_pct']*100:.2f}%"
        )
        opened = open_neg_risk_position(opp, bankroll)
        opened_total.extend(opened)

    return {
        "events_seen": len(by_event),
        "opportunities": len(opportunities),
        "opened": opened_total,
    }
