"""Hardcoded risk controls — not configurable to avoid foot-gun edits.

The numbers in this file are the consensus from a 9-model OpenRouter debate
on April 30, 2026, cross-validated against the Chaincatcher 95M-transaction
Polymarket study. Don't edit them without re-running validation.
"""
from dataclasses import dataclass


import os as _os

# EXPLORE mode = paper-only, wider price band for learning which sub-bucket
# actually wins. Sports always excluded regardless of mode (the bond strategy
# is for near-resolved certainty, NOT pre-match favorites — those carry real
# upset risk and Vegas already prices them efficiently).
EXPLORE = _os.environ.get("EXPLORE", "true").lower() == "true"


@dataclass(frozen=True)
class RiskConfig:
    # Bond entry filters — TRUE BOND ZONE only.
    # 0.95-0.99 is where outcomes are essentially already known and waiting
    # to settle. Below 0.95 there's real binary risk that doesn't fit the
    # bond thesis.
    # EXPLORE just widens the lower bound a bit (0.92) to learn which
    # sub-band wins — but never below 0.92 (that's gambling, not bonding).
    PRICE_MIN: float = 0.92 if EXPLORE else 0.95
    PRICE_MAX: float = 0.99
    HOURS_TO_RESOLUTION_MIN: int = 6 if EXPLORE else 24
    HOURS_TO_RESOLUTION_MAX: int = 168 if EXPLORE else 120  # 7 days vs 5
    VOLUME_24H_MIN: float = 25_000.0 if EXPLORE else 50_000.0
    ORDER_BOOK_DEPTH_MIN: float = 2_000.0 if EXPLORE else 5_000.0

    # Sizing — paper mode keeps it small so we can hold many positions
    POSITION_FRACTION_MAX: float = 0.01 if EXPLORE else 0.05
    POSITION_DOLLAR_CAP: float = 200.0 if EXPLORE else 2_500.0
    KELLY_FRACTION: float = 0.5  # half-Kelly always
    MAX_CONCURRENT_POSITIONS: int = 200 if EXPLORE else 15
    MAX_CATEGORY_FRACTION: float = 0.50 if EXPLORE else 0.30

    # Kill switches
    DRAWDOWN_24H_KILL: float = -0.10  # -10% in 24h pauses new trades
    STOP_LOSS_PRICE: float = 0.85  # exit if position drops to this

    # Polygon gas
    GAS_PRICE_CAP_GWEI: int = 100

    # Categories to NEVER trade — doomer + sports + ambiguous.
    # Sports are excluded because pre-match favorites at 0.95 still have
    # real upset risk; Vegas prices them efficiently; no edge.
    BLACKLIST_CATEGORIES: frozenset = frozenset({
        "war", "nuclear", "death", "scandal", "celebrity",
        "political-extreme", "doom", "apocalypse",
        "sports", "soccer", "football", "basketball", "baseball",
        "hockey", "tennis", "mma", "boxing", "ufc", "esports",
    })

    # Question-text patterns that signal a sports/uncertain-outcome match.
    # Bonds are for "is it Tuesday yet?" style markets, NOT "will Liverpool
    # beat Chelsea?" — even at 0.95, the soccer match has real binary risk.
    BLACKLIST_QUESTION_PATTERNS: tuple = (
        " vs ", " v ", " beats ", " beat ", " wins ", " win ",
        " defeats ", " defeat ", " advance", " advances",
        " score ", " scores ", " goal", " goals",
        "match ", "fight", "boxing", "playoff",
        "premier league", "la liga", "champions league", "world cup",
        "nba", "nfl", "mlb", "nhl", "ufc", "f1 ", "formula 1",
    )

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
    """Tag positions with their entry band so we can later compare win rates.
    Buckets cover the true bond zone only (0.92-0.99). Anything below isn't
    bond strategy — it's gambling on inherent uncertainty."""
    if price < 0.93: return "0.92-0.93"
    if price < 0.95: return "0.93-0.95"
    if price < 0.97: return "0.95-0.97"
    if price < 0.98: return "0.97-0.98"
    return "0.98-0.99"


RISK = RiskConfig()
BOT = BotConfig()
