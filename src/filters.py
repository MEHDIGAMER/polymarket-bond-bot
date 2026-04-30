"""Bond candidate filtering. Pure functions, easy to unit-test."""
from datetime import datetime, timezone
from typing import Any

from .config import RISK


def parse_outcome_prices(market: dict) -> tuple[float, float] | None:
    """Polymarket Gamma returns outcomePrices as a JSON-encoded string list."""
    raw = market.get("outcomePrices")
    if not raw:
        return None
    if isinstance(raw, str):
        import json
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


def hours_until(end_date_iso: str) -> float | None:
    if not end_date_iso:
        return None
    try:
        end = datetime.fromisoformat(end_date_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    delta = end - datetime.now(timezone.utc)
    return delta.total_seconds() / 3600


def has_ambiguous_resolution(market: dict) -> bool:
    """NLP-light filter — skip markets whose rules contain ambiguity flags."""
    rules = (market.get("description") or "").lower()
    rules += " " + (market.get("resolutionSource") or "").lower()
    return any(kw in rules for kw in RISK.AMBIGUOUS_KEYWORDS)


def category_blacklisted(market: dict) -> bool:
    cat = (market.get("category") or "").lower()
    tags = " ".join((market.get("tags") or [])).lower()
    question = (market.get("question") or "").lower()

    # Category/tag match — broad
    if any(blk in f"{cat} {tags}" for blk in RISK.BLACKLIST_CATEGORIES):
        return True
    # Question-text match — catches sports questions even when category is empty
    # (Polymarket often leaves category blank for pre-match favorites).
    if any(pat in question for pat in RISK.BLACKLIST_QUESTION_PATTERNS):
        return True
    # Doomer / catastrophic
    if any(blk in question for blk in {
        "nuclear", "world war", "apocalypse", "extinction", "asteroid"
    }):
        return True
    return False


def evaluate_market(market: dict) -> tuple[str, dict[str, Any]]:
    """Returns (decision, context). Decision = 'BUY-YES' | 'BUY-NO' | 'SKIP'.

    Context contains the side, price, hours-to-resolution, why-skipped if any.
    """
    ctx: dict[str, Any] = {
        "market_id": market.get("id") or market.get("conditionId"),
        "question": market.get("question", "")[:120],
    }

    if not market.get("active") or market.get("closed"):
        ctx["reason"] = "inactive_or_closed"
        return "SKIP", ctx

    prices = parse_outcome_prices(market)
    if not prices:
        ctx["reason"] = "no_prices"
        return "SKIP", ctx
    yes_price, no_price = prices
    ctx["yes_price"] = yes_price
    ctx["no_price"] = no_price

    # Pick the side that's in the bond zone (one of them likely is).
    if RISK.PRICE_MIN <= yes_price <= RISK.PRICE_MAX:
        side, side_price = "YES", yes_price
    elif RISK.PRICE_MIN <= no_price <= RISK.PRICE_MAX:
        side, side_price = "NO", no_price
    else:
        ctx["reason"] = f"outside_band ({yes_price=}, {no_price=})"
        return "SKIP", ctx
    ctx["side"] = side
    ctx["side_price"] = side_price

    hours = hours_until(market.get("endDate", ""))
    ctx["hours_to_resolution"] = hours
    if hours is None:
        ctx["reason"] = "no_end_date"
        return "SKIP", ctx
    if not (RISK.HOURS_TO_RESOLUTION_MIN <= hours <= RISK.HOURS_TO_RESOLUTION_MAX):
        ctx["reason"] = f"resolution_window_miss ({hours:.1f}h)"
        return "SKIP", ctx

    volume = float(market.get("volume", 0) or 0)
    ctx["volume"] = volume
    if volume < RISK.VOLUME_24H_MIN:
        ctx["reason"] = f"low_volume (${volume:,.0f})"
        return "SKIP", ctx

    if has_ambiguous_resolution(market):
        ctx["reason"] = "ambiguous_resolution_rules"
        return "SKIP", ctx

    if category_blacklisted(market):
        ctx["reason"] = "blacklisted_category"
        return "SKIP", ctx

    ctx["category"] = market.get("category") or "uncategorized"
    ctx["end_date"] = market.get("endDate")
    return f"BUY-{side}", ctx


def kelly_size(*, edge: float, odds: float, bankroll: float) -> float:
    """Half-Kelly with hard caps. edge = (true_prob - market_price)."""
    if edge <= 0 or odds <= 0:
        return 0.0
    kelly_full = edge / odds
    half = kelly_full * RISK.KELLY_FRACTION
    fraction_capped = min(half, RISK.POSITION_FRACTION_MAX)
    return min(fraction_capped * bankroll, RISK.POSITION_DOLLAR_CAP)
