"""Sanity-check the collected Polymarket dataset.

Reports the numbers that matter for Track 2: thematic diversity (distinct events
per domain), the per-event market cap, and price-series coverage.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "polymarket"
DOMAINS = ("politics", "finance", "sports")


def main() -> None:
    contracts = [json.loads(l) for l in (RAW / "contracts.jsonl").open()]
    snaps_per_market: Counter[str] = Counter()
    with (RAW / "prices.jsonl").open() as f:
        for line in f:
            snaps_per_market[json.loads(line)["market_id"]] += 1

    print(f"CONTRATTI TOTALI: {len(contracts)}")
    print(f"SNAPSHOT TOTALI:  {sum(snaps_per_market.values())}")

    empty = [c for c in contracts if snaps_per_market[c["market_id"]] == 0]
    print(f"CONTRATTI CON SERIE VUOTA: {len(empty)}")

    counts = [snaps_per_market[c["market_id"]] for c in contracts]
    if counts:
        print(f"SNAPSHOT/CONTRATTO: mediana {statistics.median(counts):.0f}, "
              f"min {min(counts)}, max {max(counts)}")

    print(f"\nOUTCOME: {dict(Counter(c['resolution_outcome'] for c in contracts))}")

    for d in DOMAINS:
        sub = [c for c in contracts if c["category"] == d]
        per_event = Counter(c.get("event_id") or c["event_title"] for c in sub)
        titles = {}
        for c in sub:
            titles[c.get("event_id") or c["event_title"]] = c["event_title"]

        print(f"\n=== {d.upper()} ===")
        print(f"contratti: {len(sub)}  (requisito hard: >=100 -> "
              f"{'OK' if len(sub) >= 100 else 'FAIL'})")
        print(f"eventi distinti: {len(per_event)}")
        print(f"max market per evento: {max(per_event.values()) if per_event else 0} "
              f"(cap 3 -> {'OK' if per_event and max(per_event.values()) <= 3 else 'FAIL'})")
        print(f"distribuzione market/evento: "
              f"{dict(sorted(Counter(per_event.values()).items()))}")
        print("top 10 eventi:")
        for ev, n in per_event.most_common(10):
            print(f"   {n}x  {titles[ev][:70]}")


if __name__ == "__main__":
    main()
