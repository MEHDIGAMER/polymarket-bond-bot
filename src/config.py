"""Hardcoded risk controls — not configurable to avoid foot-gun edits.

The numbers in this file are the consensus from a 9-model OpenRouter debate
on April 30, 2026, cross-validated against the Chaincatcher 95M-transaction
Polymarket study. Don't edit them without re-running validation.
"""
from dataclasses import dataclass


import os as _os

# EXPLORE mode = paper-only, wider filters, more positions per day so we
# learn which entry-bucket actually wins. Set EXPLORE=true in .env to enable.
EXPLORE = _os.environ.get("EXPLORE", "true").lower() == "true"


@dataclass(frozen=True)
class RiskConfig:
    # Bond entry filters
    # In EXPLORE mode: 0.80-0.99 (wide net, lots of paper trades).
    # In production:   0.93-0.97 (debate-validated whale sweet spot).
    PRICE_MIN: float = 0.80 if EXPLORE else 0.93
    PRICE_MAX: float = 0.99 if EXPLORE else 0.97
    HOURS_TO_RESOLUTION_MIN: int = 6 if EXPLORE else 24
    HOURS_TO_RESOLUTION_MAX: int = 168 if EXPLORE else 120  # 7 days vs 5
    VOLUME_24H_MIN: float = 5_000.0 if EXPLORE else 50_000.0
    ORDER_BOOK_DEPTH_MIN: float = 1_000.0 if EXPLORE else 5_000.0

    # Sizing — paper mode keeps it tiny so we can hold 50+ concurrent positions
    POSITION_FRACTION_MAX: float = 0.01 if EXPLORE else 0.05  # 1% per pos in EXPLORE
    POSITION_DOLLAR_CAP: float = 200.0 if EXPLORE else 2_500.0
    KELLY_FRACTION: float = 0.5  # half-Kelly always
    MAX_CONCURRENT_POSITIONS: int = 200 if EXPLORE else 15
    MAX_CATEGORY_FRACTION: float = 0.50 if EXPLORE else 0.30

    # Kill switches
    DRAWDOWN_24H_KILL: float = -0.10  # -10% in 24h pauses new trades
    STOP_LOSS_PRICE: float = 0.85  # exit if position drops to this

    # Polygon gas
    GAS_PRICE_CAP_GWEI: int = 100

    # Categories to NEVER trade (doomer / political / ambiguous)
    BLACKLIST_CATEGORIES: frozenset = frozenset({
        "war", "nuclear", "death", "scandal", "celebrity",
        "political-extreme", "doom", "apocalypse",
    })

    # Resolution-source ambiguity flags (skip if any present in rules)
    AMBIGUOUS_KEYWORDS: tuple = (
        "subjective", "discretion", "consensus of media",
        "reasonable interpretation", "considered", "deemed",
        "according to", "or similar", "approximately",
    )


@dataclass(frozen=True)
class BotConfig:
    MODE: str = "PAPER"  # "PAPER" | "LIVE-SMALL" | "LIVE-AUTO" | "LIVE-FULL"
    PAPER_BANKROLL: float = 10_000.0  # virtual money for paper-trade phase
    # Faster scan in EXPLORE mode so we don't miss new markets entering the band
    SCAN_INTERVAL_SECONDS: int = 30 if EXPLORE else 60
    # Pull ALL active markets, paginated. EXPLORE = wider net.
    MAX_MARKETS_PER_SCAN: int = 5000 if EXPLORE else 1000
    GAMMA_API_BASE: str = "https://gamma-api.polymarket.com"
    CLOB_API_BASE: str = "https://clob.polymarket.com"
    DATABASE_PATH: str = "data/bot.db"
    LOG_PATH: str = "logs/bot.log"


def price_bucket(price: float) -> str:
    """Tag positions with their entry band so we can later compare win rates."""
    if price < 0.85: return "0.80-0.85"
    if price < 0.90: return "0.85-0.90"
    if price < 0.93: return "0.90-0.93"
    if price < 0.95: return "0.93-0.95"
    if price < 0.97: return "0.95-0.97"
    return "0.97-0.99"


RISK = RiskConfig()
BOT = BotConfig()
