"""Math + safety-net tests for the negative-risk arbitrage scanner."""
import json
from datetime import datetime, timezone, timedelta

from src.neg_risk import (
    parse_no_price, group_event_outcomes, evaluate_event, _is_catchall,
)


def _market(event_id="evt-1", no_price=0.20, question="Will Candidate A win the primary?",
            active=True, closed=False, group_title="", negRisk=True):
    end = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat().replace("+00:00", "Z")
    yes_p = round(1.0 - no_price, 4)
    return {
        "id": f"{event_id}-{question[:10]}",
        # Polymarket nests event metadata in an array — match the real shape
        "events": [{"id": event_id, "ticker": event_id, "slug": event_id}],
        "negRisk": negRisk,
        "question": question,
        "groupItemTitle": group_title or question,
        "outcomePrices": json.dumps([str(yes_p), str(no_price)]),
        "active": active, "closed": closed, "endDate": end,
        "volume": 200_000,
    }


def test_parse_no_price_string_json():
    assert parse_no_price(_market(no_price=0.18)) == 0.18


def test_parse_no_price_native_list():
    m = _market(); m["outcomePrices"] = ["0.7", "0.3"]
    assert parse_no_price(m) == 0.3


def test_parse_no_price_invalid():
    m = _market(); m["outcomePrices"] = "not json"
    assert parse_no_price(m) is None


def test_grouping_by_event_id():
    markets = [_market(event_id="X", question="A wins"),
               _market(event_id="X", question="B wins"),
               _market(event_id="Y", question="C wins")]
    grouped = group_event_outcomes(markets)
    assert "X" in grouped and "Y" in grouped
    assert len(grouped["X"]) == 2 and len(grouped["Y"]) == 1


def test_arb_when_math_holds():
    # 5-way event, NO prices sum to 3.50 → threshold 4 × 0.98 = 3.92
    legs = [_market(event_id="E", no_price=p, question=f"C{i} wins")
            for i, p in enumerate([0.70, 0.70, 0.70, 0.70, 0.70])]
    opp = evaluate_event("E", legs)
    assert opp is not None, "should find arb"
    assert opp["n_outcomes"] == 5
    assert abs(opp["sum_no"] - 3.50) < 0.001
    assert opp["edge_pct"] > 0.10  # >10% edge


def test_no_arb_when_sum_too_high():
    # 5-way, sum NO = 3.95 → threshold 3.92 → fails
    legs = [_market(event_id="E2", no_price=0.79, question=f"C{i} wins")
            for i in range(5)]
    assert evaluate_event("E2", legs) is None


def test_skip_when_too_few_outcomes():
    legs = [_market(event_id="E3", no_price=0.30, question=f"C{i} wins")
            for i in range(2)]
    assert evaluate_event("E3", legs) is None


def test_skip_when_none_of_above():
    legs = [_market(event_id="E4", no_price=0.30, question="A wins"),
            _market(event_id="E4", no_price=0.30, question="B wins"),
            _market(event_id="E4", no_price=0.30, question="C wins"),
            _market(event_id="E4", no_price=0.30, question="None of the above")]
    assert evaluate_event("E4", legs) is None, "must skip on catchall"


def test_skip_when_other_outcome():
    legs = [_market(event_id="E5", no_price=0.30, question="A wins"),
            _market(event_id="E5", no_price=0.30, question="B wins"),
            _market(event_id="E5", no_price=0.30, question="C wins"),
            _market(event_id="E5", no_price=0.30, question="Other")]
    assert evaluate_event("E5", legs) is None


def test_catchall_detection():
    assert _is_catchall("None of the above")
    assert _is_catchall("Other candidate")
    assert _is_catchall("Anyone else")
    assert _is_catchall("Someone else")
    assert not _is_catchall("Bernie Sanders")
    assert not _is_catchall("Will the Fed cut rates?")


def test_edge_calculation_correct():
    # 4-way, NO = 0.55 each, sum = 2.20, max payout = 3.0
    # edge = (3.0 - 2.20) / 2.20 = 36.4%  (under 50% cap)
    legs = [_market(event_id="E6", no_price=0.55, question=f"C{i} wins")
            for i in range(4)]
    opp = evaluate_event("E6", legs)
    assert opp is not None, "should find arb"
    assert abs(opp["edge_pct"] - 0.3636) < 0.01


def test_skip_dead_market_low_prices():
    # Stale market: NO prices all collapsed to 0.02 → suspicious, skip
    legs = [_market(event_id="DEAD", no_price=0.02, question=f"C{i} wins")
            for i in range(5)]
    assert evaluate_event("DEAD", legs) is None


def test_skip_dead_market_high_prices():
    # Stale market: NO prices all near 1.0 → likely already resolved
    legs = [_market(event_id="DEAD2", no_price=0.99, question=f"C{i} wins")
            for i in range(5)]
    assert evaluate_event("DEAD2", legs) is None


def test_skip_oversized_event():
    # 15-way event — math holds but too capital-intensive for paper phase
    legs = [_market(event_id="BIG", no_price=0.85, question=f"C{i} wins")
            for i in range(15)]
    assert evaluate_event("BIG", legs) is None


def test_skip_when_not_neg_risk_event():
    """Independent-prop markets (no negRisk flag) must be excluded — these
    are cricket/sports-style 'multiple yes/no on one match' that break math."""
    legs = [_market(event_id="CRICKET", no_price=0.50,
                    question="Toss winner — Nepal", negRisk=False)
            for _ in range(3)]
    grouped = group_event_outcomes(legs)
    # negRisk=false means group_event_outcomes filters them out entirely
    assert "CRICKET" not in grouped, \
        f"non-negRisk events must be excluded, got {list(grouped.keys())}"


def test_skip_sports_keywords_in_question():
    """Even with negRisk=true, blacklist sports/match patterns."""
    legs = [_market(event_id="MATCH", no_price=0.30,
                    question="Liverpool vs Chelsea — Liverpool wins")
            for _ in range(3)]
    grouped = group_event_outcomes(legs)
    assert "MATCH" not in grouped


def test_legitimate_election_passes_filter():
    """A clean political multi-candidate election should pass."""
    legs = [_market(event_id="ELECTION", no_price=0.30,
                    question=f"Will Candidate {chr(65+i)} win the 2026 primary?",
                    negRisk=True)
            for i in range(5)]
    grouped = group_event_outcomes(legs)
    assert "ELECTION" in grouped
    assert len(grouped["ELECTION"]) == 5


def test_skip_unrealistic_edge():
    # Sum NO = 0.5 in a 5-way → edge = (4 - 0.5) / 0.5 = 700%
    # Almost certainly stale data, must skip
    legs = [_market(event_id="STALE", no_price=0.10, question=f"C{i} wins")
            for i in range(5)]
    # Each leg passes the 0.05 floor, but edge will be way >50%
    assert evaluate_event("STALE", legs) is None


if __name__ == "__main__":
    fns = [v for k, v in globals().items() if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn(); print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}"); failed += 1
        except Exception as e:
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}"); failed += 1
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    raise SystemExit(failed)
