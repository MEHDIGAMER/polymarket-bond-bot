"""Smoke tests for the filter logic. Runs offline — no API calls."""
import json
from datetime import datetime, timezone, timedelta

from src.config import RISK
from src.filters import (
    parse_outcome_prices, hours_until, has_ambiguous_resolution,
    category_blacklisted, evaluate_market, kelly_size,
)


def _market(**overrides):
    """Build a synthetic market dict with sensible defaults for a bond candidate."""
    end = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat().replace("+00:00", "Z")
    base = {
        "id": "test-1",
        "question": "Will the Fed cut rates at the May meeting?",
        "outcomePrices": json.dumps(["0.95", "0.05"]),
        "volume": 200_000,
        "endDate": end,
        "active": True,
        "closed": False,
        "category": "economy",
        "description": "Resolves YES if the FOMC announces a rate cut at the May 2026 meeting.",
        "resolutionSource": "https://federalreserve.gov",
        "tags": ["fed", "rates"],
    }
    base.update(overrides)
    return base


def test_parse_prices_string():
    p = parse_outcome_prices(_market())
    assert p == (0.95, 0.05), p


def test_parse_prices_list():
    m = _market(outcomePrices=["0.97", "0.03"])
    assert parse_outcome_prices(m) == (0.97, 0.03)


def test_hours_until_positive():
    end = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat().replace("+00:00", "Z")
    h = hours_until(end)
    assert 47 < h < 49, h


def test_ambiguous_resolution():
    m = _market(description="Resolves at the discretion of the moderator.")
    assert has_ambiguous_resolution(m) is True
    assert has_ambiguous_resolution(_market()) is False


def test_blacklist():
    assert category_blacklisted(_market(category="war")) is True
    assert category_blacklisted(_market(question="will nuclear weapons be used?")) is True
    assert category_blacklisted(_market()) is False


def test_evaluate_buy_yes():
    decision, ctx = evaluate_market(_market())
    assert decision == "BUY-YES", (decision, ctx)
    assert ctx["side"] == "YES"
    assert ctx["side_price"] == 0.95


def test_evaluate_buy_no():
    m = _market(outcomePrices=json.dumps(["0.05", "0.95"]))
    decision, ctx = evaluate_market(m)
    assert decision == "BUY-NO", (decision, ctx)
    assert ctx["side_price"] == 0.95


def test_evaluate_skip_low_volume():
    decision, ctx = evaluate_market(_market(volume=1_000))
    assert decision == "SKIP"
    assert "low_volume" in ctx["reason"]


def test_evaluate_skip_outside_band():
    decision, ctx = evaluate_market(_market(outcomePrices=json.dumps(["0.50", "0.50"])))
    assert decision == "SKIP"
    assert "outside_band" in ctx["reason"]


def test_evaluate_skip_too_close_to_resolution():
    end = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    decision, ctx = evaluate_market(_market(endDate=end))
    assert decision == "SKIP"
    assert "resolution_window" in ctx["reason"]


def test_evaluate_skip_too_far_from_resolution():
    end = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat().replace("+00:00", "Z")
    decision, ctx = evaluate_market(_market(endDate=end))
    assert decision == "SKIP"
    assert "resolution_window" in ctx["reason"]


def test_kelly_size_caps():
    # Edge of 5% on a 0.95 market, $100K bankroll
    # Kelly_full = 0.05 / (0.95/0.05) = 0.05 / 19 ≈ 0.26%
    # Half-Kelly ≈ 0.13% of bankroll = $130
    size = kelly_size(edge=0.05, odds=19.0, bankroll=100_000)
    assert 100 < size < 200, size

    # Sanity — never exceed dollar cap regardless of inputs
    size = kelly_size(edge=0.5, odds=1.0, bankroll=10_000_000)
    assert size <= RISK.POSITION_DOLLAR_CAP, size

    # Negative edge → 0
    assert kelly_size(edge=-0.01, odds=1.0, bankroll=10_000) == 0.0


if __name__ == "__main__":
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
            failed += 1
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(failed)
