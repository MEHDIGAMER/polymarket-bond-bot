"""Hardcoded risk controls — not configurable to avoid foot-gun edits.

The numbers in this file are the consensus from a 9-model OpenRouter debate
on April 30, 2026, cross-validated against the Chaincatcher 95M-transaction
Polymarket study. Don't edit them without re-running validation.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    # Bond entry filters
    PRICE_MIN: float = 0.93
    PRICE_MAX: float = 0.97
    HOURS_TO_RESOLUTION_MIN: int = 24
    HOURS_TO_RESOLUTION_MAX: int = 120  # 5 days
    VOLUME_24H_MIN: float = 50_000.0
    ORDER_BOOK_DEPTH_MIN: float = 5_000.0  # within 1% of mid

    # Sizing
    POSITION_FRACTION_MAX: float = 0.05  # 5% of bankroll
    POSITION_DOLLAR_CAP: float = 2_500.0  # absolute cap
    KELLY_FRACTION: float = 0.5  # half-Kelly
    MAX_CONCURRENT_POSITIONS: int = 15
    MAX_CATEGORY_FRACTION: float = 0.30  # 30% in any single category

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
    SCAN_INTERVAL_SECONDS: int = 60
    GAMMA_API_BASE: str = "https://gamma-api.polymarket.com"
    CLOB_API_BASE: str = "https://clob.polymarket.com"
    DATABASE_PATH: str = "data/bot.db"
    LOG_PATH: str = "logs/bot.log"


RISK = RiskConfig()
BOT = BotConfig()
