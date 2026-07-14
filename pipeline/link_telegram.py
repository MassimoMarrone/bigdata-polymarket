"""Link Telegram messages to contracts with the same funnel used for Bluesky.

Bluesky's keyword stage happened server-side (we could only search, not download
the platform). Telegram we downloaded whole, so the keyword stage runs locally —
but it is the *same* stage: the same keywords, ANDed, inside the contract's
lifetime. Only then does the semantic filter apply. Keeping the funnel identical
is what makes the cross-platform comparison in Task 2.4 mean anything.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = RAW / "telegram" / "linked.jsonl"

MIN_TERMS = 2  # a single shared word is not evidence of aboutness


def _kw(question: str) -> list[str]:
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from bluesky import keywords
    return keywords(question, n=4).lower().split()


def main() -> None:
    contracts = [json.loads(line) for line in
                 (RAW / "polymarket" / "contracts.jsonl").open()]
    messages = [json.loads(line) for line in
                (RAW / "telegram" / "messages.jsonl").open()]
    print(f"{len(messages)} messaggi Telegram, {len(contracts)} contratti")

    # Index messages by day, so each contract only scans its own lifetime.
    by_day: dict[str, list[dict]] = {}
    for m in messages:
        day = m["published_at"][:10]
        by_day.setdefault(day, []).append(m)

    n_links = 0
    covered = 0
    with OUT.open("w") as f:
        for c in contracts:
            terms = _kw(c["question"])
            if not terms:
                continue
            start = c["creation_date"][:10]
            end = c["close_date"][:10]
            hits = 0
            for day, msgs in by_day.items():
                if not (start <= day <= end):
                    continue
                for m in msgs:
                    text = m["text"].lower()
                    matched = sum(t in text for t in terms)
                    # Same AND-ish semantics as Bluesky search, relaxed to a
                    # majority of terms: Telegram headlines are terser than posts.
                    if matched >= max(MIN_TERMS, len(terms) - 1):
                        row = dict(m)
                        row["market_id"] = c["market_id"]
                        row["category"] = c["category"]
                        row["search_query"] = " ".join(terms)
                        f.write(json.dumps(row) + "\n")
                        hits += 1
            n_links += hits
            covered += hits >= 5
    print(f"{n_links} link (messaggio, contratto) -> {OUT}")
    print(f"contratti con >=5 messaggi Telegram: {covered}/{len(contracts)} "
          f"({100*covered/len(contracts):.0f}%)")


if __name__ == "__main__":
    main()
