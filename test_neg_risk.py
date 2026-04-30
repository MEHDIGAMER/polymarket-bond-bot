"""Math + safety-net tests for the negative-risk arbitrage scanner."""
import json
from datetime import datetime, timezone, timedelta

from src.neg_risk import (
    parse_no_price, group_event_outcomes, evaluate_event, _is_catchall,
)


def _market(event_id="evt-1", no_price=0.20, question="Will A win?",
            active=True, closed=False, group_title=""):
    end = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat().replace("+00:00", "Z")
    yes_p = round(1.0 - no_price, 4)
    return {
        "id": f"{event_id}-{question[:10]}",
        "eventId": event_id,
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
    # 4-way, NO = 0.50 each, sum = 2.0, max payout = 3.0
    # edge = (3.0 - 2.0) / 2.0 = 50%
    legs = [_market(event_id="E6", no_price=0.50, question=f"C{i} wins")
            for i in range(4)]
    opp = evaluate_event("E6", legs)
    assert opp is not None
    assert abs(opp["edge_pct"] - 0.50) < 0.001


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
