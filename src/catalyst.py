"""Calendar Catalyst engine.

Pre-loaded list of telegraphed macro events with predictable Polymarket
positioning. Panel-validated for May 2026.

Each catalyst defines:
  • date — when the event happens (UTC)
  • match_keywords — patterns to find the relevant Polymarket market
  • side — YES or NO bond on the favored direction
  • min_price / max_price — only enter if market sits in this band
  • base_rate_win — historical win rate for this catalyst pattern (informational)
"""
from datetime import datetime, timezone
from dataclasses import dataclass
import logging
import re

from .config import RISK, BOT
from . import db
from .events import emit_position_opened


log = logging.getLogger("catalyst")


@dataclass(frozen=True)
class Catalyst:
    name: str
    date_utc: str        # ISO date (resolution day)
    match_keywords: tuple
    side: str            # "YES" or "NO"
    min_price: float
    max_price: float
    base_rate_win: float
    notes: str


CATALYSTS: tuple = (
    Catalyst(
        name="FOMC May 2026 Meeting",
        date_utc="2026-05-07",
        match_keywords=("fed", "fomc", "rate decision", "fed funds rate"),
        side="YES",
        min_price=0.93, max_price=0.99,
        base_rate_win=0.92,
        notes="Dot plot already telegraphed. Bond on YES if 'Fed holds' market exists.",
    ),
    Catalyst(
        name="Nonfarm Payrolls May",
        date_utc="2026-05-02",
        match_keywords=("nonfarm payroll", "nfp", "jobs report", "unemployment rate"),
        side="YES",
        min_price=0.92, max_price=0.99,
        base_rate_win=0.85,
        notes="Pre-position on consensus matching forecast.",
    ),
    Catalyst(
        name="Apple Earnings Q2 2026",
        date_utc="2026-05-03",
        match_keywords=("apple earnings", "aapl", "apple revenue"),
        side="YES",
        min_price=0.92, max_price=0.99,
        base_rate_win=0.82,
        notes="Whisper number typically beats by Day -2.",
    ),
    Catalyst(
        name="CPI May Release",
        date_utc="2026-05-12",
        match_keywords=("cpi", "consumer price index", "inflation report"),
        side="YES",
        min_price=0.92, max_price=0.99,
        base_rate_win=0.85,
        notes="Cleveland Fed nowcast aligns 48h before release.",
    ),
    Catalyst(
        name="Nvidia Earnings Q1",
        date_utc="2026-05-22",
        match_keywords=("nvidia", "nvda earnings", "nvda revenue"),
        side="YES",
        min_price=0.92, max_price=0.99,
        base_rate_win=0.88,
        notes="Hyperscaler capex pre-leaks the beat.",
    ),
    Catalyst(
        name="ECB Rate Decision",
        date_utc="2026-05-08",
        match_keywords=("ecb", "european central bank", "lagarde", "euro rates"),
        side="YES",
        min_price=0.93, max_price=0.99,
        base_rate_win=0.90,
        notes="ECB telegraphs via speakers in 2 weeks prior.",
    ),
    Catalyst(
        name="OPEC Meeting May",
        date_utc="2026-05-15",
        match_keywords=("opec", "oil cut", "saudi production"),
        side="YES",
        min_price=0.90, max_price=0.99,
        base_rate_win=0.83,
        notes="OPEC pre-announces decisions ~10 days ahead.",
    ),
    Catalyst(
        name="PCE Inflation Release",
        date_utc="2026-05-30",
        match_keywords=("pce", "personal consumption", "core pce"),
        side="YES",
        min_price=0.91, max_price=0.99,
        base_rate_win=0.84,
        notes="Track CPI relationship 2 weeks prior.",
    ),
    Catalyst(
        name="Microsoft Earnings",
        date_utc="2026-05-15",
        match_keywords=("microsoft", "msft earnings", "azure revenue"),
        side="YES",
        min_price=0.92, max_price=0.99,
        base_rate_win=0.85,
        notes="Azure growth pre-leaks via partner channels.",
    ),
    Catalyst(
        name="Q1 GDP Release",
        date_utc="2026-05-01",
        match_keywords=("gdp", "q1 gdp", "advance gdp"),
        side="YES",
        min_price=0.90, max_price=0.99,
        base_rate_win=0.86,
        notes="Atlanta Fed GDPNow within 0.3% of advance number 99% of the time.",
    ),
)


def _question_matches(question: str, keywords: tuple) -> bool:
    q = (question or "").lower()
    return any(kw in q for kw in keywords)


def _hours_until(end_date_iso: str) -> float | None:
    if not end_date_iso:
        return None
    try:
        end = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (end - datetime.now(timezone.utc)).total_seconds() / 3600


def _get_yes_no_prices(market: dict) -> tuple[float, float] | None:
    import json
    raw = market.get("outcomePrices")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw, list) or len(raw) < 2:
        return None
    try:
        return float(raw[0]), float(raw[1])
    except (ValueError, TypeError):
        return None


def find_active_catalysts(now: datetime | None = None) -> list[Catalyst]:
    """Catalysts whose resolution date is within the next 7 days."""
    now = now or datetime.now(timezone.utc)
    out: list[Catalyst] = []
    for c in CATALYSTS:
        try:
            event_date = datetime.fromisoformat(c.date_utc + "T23:59:59+00:00")
        except ValueError:
            continue
        days = (event_date - now).total_seconds() / 86400
        if -1 <= days <= 7:  # not yet resolved + not more than a week out
            out.append(c)
    return out


def scan(markets: list[dict], bankroll: float) -> dict:
    """Match active catalysts against current Polymarket markets, open positions."""
    active = find_active_catalysts()
    if not active:
        return {"active_catalysts": 0, "matches": 0, "opened": []}

    opened: list[dict] = []
    matches = 0

    for c in active:
        for m in markets:
            question = m.get("question") or ""
            if not _question_matches(question, c.match_keywords):
                continue
            if not m.get("active") or m.get("closed"):
                continue

            prices = _get_yes_no_prices(m)
            if not prices:
                continue
            yes_p, no_p = prices
            target_price = yes_p if c.side == "YES" else no_p

            if not (c.min_price <= target_price <= c.max_price):
                continue

            hours = _hours_until(m.get("endDate", ""))
            if hours is None or hours < 0 or hours > 168:
                continue

            market_id = m.get("id") or m.get("conditionId")
            if not market_id or db.already_holding(market_id):
                continue

            matches += 1
            size_usd = min(bankroll * 0.02, 200)  # 2% of bankroll, $200 cap
            shares = size_usd / target_price
            pos_id = db.insert_position(
                market_id=market_id,
                market_question=question[:120],
                side=c.side,
                entry_price=target_price,
                size_usd=size_usd,
                shares=shares,
                end_date=m.get("endDate") or c.date_utc,
                category=f"CATALYST:{c.name}",
                mode=BOT.MODE,
                metadata={
                    "strategy": "catalyst",
                    "catalyst_name": c.name,
                    "base_rate_win": c.base_rate_win,
                },
            )
            pos = {
                "id": pos_id,
                "market_id": market_id,
                "question": question[:120],
                "side": c.side,
                "entry_price": target_price,
                "size_usd": size_usd,
                "shares": shares,
                "category": f"CATALYST:{c.name}",
            }
            opened.append(pos)
            emit_position_opened(pos)
            log.info(f"CATALYST match: {c.name} → {c.side} ${size_usd:.2f} @ {target_price}")

    return {
        "active_catalysts": len(active),
        "matches": matches,
        "opened": opened,
    }
