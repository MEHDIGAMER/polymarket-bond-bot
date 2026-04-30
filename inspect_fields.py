"""One-off: inspect Polymarket Gamma fields to find the negRisk flag."""
from src import poly_api

markets = poly_api.list_active_markets(limit=200)
print(f"Got {len(markets)} markets")

sample = markets[0]
print("=== Field names containing neg/risk/event/group ===")
for k in sorted(sample.keys()):
    if any(s in k.lower() for s in ["neg", "risk", "event", "group"]):
        print(f"  {k} = {repr(sample[k])[:150]}")
print()

# Test a few possible field names
for name in ["negRisk", "neg_risk", "negativeRisk", "isNegativeRisk",
             "negative_risk", "exclusiveOutcomes", "isMutuallyExclusive"]:
    n_true = sum(1 for m in markets if m.get(name) is True)
    n_strue = sum(1 for m in markets if str(m.get(name, "")).lower() == "true")
    if n_true or n_strue:
        print(f"{name}: bool={n_true} str={n_strue}")

print("\n=== eventId distribution ===")
from collections import Counter
event_counts = Counter(m.get("eventId") or m.get("event_id") for m in markets)
multi_event = {e: c for e, c in event_counts.items() if c > 1 and e}
print(f"Markets grouped under same eventId: {len(multi_event)} events with multiple legs")
for e, c in list(multi_event.items())[:5]:
    print(f"  eventId={str(e)[:40]} count={c}")

print("\n=== Sample market FULL field list ===")
m = markets[0]
for k in sorted(m.keys()):
    v = str(m[k])[:80]
    print(f"  {k}: {v}")
