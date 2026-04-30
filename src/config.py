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
# SAME_DAY: drop the 24h floor to 1h so we catch markets resolving today.
# Critical for day-1 math validation. Once validated, set to false.
SAME_DAY = _os.environ.get("SAME_DAY", "true").lower() == "true"

# Strategy toggles — all three on by default
STRATEGY_BOND       = _os.environ.get("STRATEGY_BOND",       "true").lower() == "true"
STRATEGY_NEG_RISK   = _os.environ.get("STRATEGY_NEG_RISK",   "true").lower() == "true"
STRATEGY_CATALYST   = _os.environ.get("STRATEGY_CATALYST",   "true").lower() == "true"


@dataclass(frozen=True)
class RiskConfig:
    # Bond entry filters — TRUE BOND ZONE only.
    # 0.95-0.99 is where outcomes are essentially already known and waiting
    # to settle. Below 0.95 there's real binary risk that doesn't fit the
    # bond thesis.
    # EXPLORE just widens the lower bound a bit (0.92) to learn which
    # sub-band wins — but never below 0.92 (that's gambling, not bonding).
    # Tightened per debate consensus: 0.97-0.99 for max win-rate confidence.
    PRICE_MIN: float = 0.97
    PRICE_MAX: float = 0.99
    HOURS_TO_RESOLUTION_MIN: int = 1 if SAME_DAY else 24
    HOURS_TO_RESOLUTION_MAX: int = 72 if EXPLORE else 120
    VOLUME_24H_MIN: float = 25_000.0 if EXPLORE else 50_000.0
    ORDER_BOOK_DEPTH_MIN: float = 2_000.0 if EXPLORE else 5_000.0
    # Negative-Risk Arb specific
    NEG_RISK_FEE_BUFFER: float = 0.02  # require 2% edge after fees
    NEG_RISK_MIN_OUTCOMES: int = 3     # event must have ≥3 candidates
    NEG_RISK_POSITION_USD: float = 100 # $100 per leg max in paper

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

    # Sport-specific question patterns. Tightened to AVOID false positives on
    # political/business markets that legitimately use "win" / "advance" verbs.
    # We accept slight risk of missing edge sports but no false sports opens.
    BLACKLIST_QUESTION_PATTERNS: tuple = (
        " vs ", " vs. ",                       # team1 vs team2
        " beats ", " defeats ",                # sports-specific verbs
        " score ", " scores ", " goal", " goals",
        "match winner", "match result",
        "fight", "boxing", "knockout",
        "playoff", "playoffs", "bracket",
        # Specific sports/match patterns — caught Premier League leak
        "win on 20", "win on may", "win on june", "win on july",
        "win on aug", "win on sep", "win on oct", "win on nov", "win on dec",
        " fc ", " fc?", " fc.", " afc ", " afc?", " cfc ",
        # Major leagues + competitions
        "premier league", "la liga", "bundesliga", "serie a",
        "champions league", "europa league", "world cup", "euros",
        "nba ", "nfl ", "mlb ", "nhl ", "ufc ", "wnba",
        "f1 ", "formula 1", "grand prix",
        "tennis", "golf", "cricket", "t20 ", "ipl ", "rugby",
        "racing", "horse race", "marathon",
        # Cricket prop styles that leaked
        "toss winner", "most sixes", "top batter", "top wicket",
        # Common soccer team suffixes (false positives unlikely on these)
        " united ", " united?", " united.", " utd ", " utd?",
        " rangers ", " rovers ", " athletic ",
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
