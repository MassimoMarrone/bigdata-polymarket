"""Collect resolved Polymarket contracts + price time series.

Domain comes from the parent event's tags: the market-level `category` field is
always null in the Gamma API. Price history needs interval=max WITH fidelity=1440;
fidelity=60 silently returns an empty series.

Selection favours THEMATIC DIVERSITY over raw volume: a single Polymarket event
can hold dozens of near-identical markets (one per Fed-Chair candidate, one per
WTI price threshold), which would collapse the contract-to-post linking onto the
same handful of keywords. We therefore cap the number of markets taken from any
one event (MAX_PER_EVENT) and walk deeper into the resolved-event list until the
per-domain quota is met. Markets whose price series comes back empty are dropped
at selection time and replaced, so every contract written out has a usable series.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterator

import requests

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

DOMAINS = ("politics", "finance", "sports")
# Quota per domain. Sports needs a bigger buffer: many sports markets last only a
# few days, so a fifth of them fall below the >=10-snapshot floor that the lead/lag
# analysis requires, and the brief's 100/domain minimum would be missed.
QUOTA = {"politics": 130, "finance": 130, "sports": 160}
MAX_PER_EVENT = 3  # thematic-diversity cap: top-3 markets by volume per event
PAGE = 100  # Gamma caps page size at 100 regardless of `limit`
MAX_OFFSET = 2100  # Gamma answers 422 beyond this offset
OVERSAMPLE = 1.5  # candidates per quota slot, to absorb markets with no price series

RAW = Path(__file__).resolve().parents[1] / "data" / "raw" / "polymarket"


def _get(url: str, params: dict, retries: int = 5) -> object:
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=60)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"request failed after {retries} attempts: {url}")


def closed_events(tag: str) -> Iterator[dict]:
    for offset in range(0, MAX_OFFSET, PAGE):
        page = _get(f"{GAMMA}/events", {
            "closed": "true", "tag_slug": tag,
            "limit": PAGE, "offset": offset,
            "order": "volume", "ascending": "false",
        })
        if not page:
            return
        yield from page
        time.sleep(0.2)
        if len(page) < PAGE:
            return


def _as_contract(m: dict, event: dict, tag: str) -> dict | None:
    """Normalise a market, or None if it is not a cleanly resolved binary bet."""
    if not m.get("closed") or not m.get("clobTokenIds"):
        return None
    prices = json.loads(m.get("outcomePrices") or "[]")
    outcomes = json.loads(m.get("outcomes") or "[]")
    if len(prices) != len(outcomes) or "1" not in prices:
        return None  # unresolved, void, or ambiguous settlement
    if not (m.get("startDate") and m.get("endDate")):
        return None
    return {
        "market_id": str(m["id"]),
        "question": m["question"],
        "category": tag,
        "outcomes": outcomes,
        "resolution_outcome": outcomes[prices.index("1")],
        "resolution_date": m.get("closedTime") or m.get("endDate"),
        "creation_date": m.get("createdAt"),
        "close_date": m.get("endDate"),
        "url": f"https://polymarket.com/event/{event.get('slug')}",
        "volume": m.get("volumeNum"),
        "event_id": str(event.get("id")),
        "event_title": event.get("title"),
        "clob_token_ids": json.loads(m["clobTokenIds"]),
    }


def event_candidates(tag: str) -> Iterator[list[dict]]:
    """Per resolved event, its markets ordered by volume (best candidates first)."""
    for event in closed_events(tag):
        markets = [
            c for c in (_as_contract(m, event, tag) for m in event.get("markets", []))
            if c is not None
        ]
        if markets:
            markets.sort(key=lambda c: c["volume"] or 0, reverse=True)
            yield markets


def price_history(token_id: str) -> list[dict]:
    data = _get(f"{CLOB}/prices-history", {
        "market": token_id, "interval": "max", "fidelity": 1440,
    })
    return data.get("history", [])


def series_for(contract: dict) -> list[dict]:
    """All price snapshots for a contract; empty if the market has no history."""
    rows: list[dict] = []
    for outcome, token in zip(contract["outcomes"], contract["clob_token_ids"]):
        for point in price_history(token):
            rows.append({
                "market_id": contract["market_id"],
                "outcome": outcome,
                "timestamp": point["t"],
                "price": point["p"],
            })
        time.sleep(0.15)
    return rows


def collect(tag: str, seen_markets: set[str]) -> tuple[list[dict], list[dict]]:
    """Contracts + price rows for one domain, <=MAX_PER_EVENT markets per event.

    Selection is metadata-only (cheap); price series are fetched afterwards, for
    the shortlist alone. Markets whose series comes back empty are dropped, which
    is why the shortlist is oversampled.
    """
    shortlist: list[dict] = []
    per_domain = QUOTA[tag]
    target = int(per_domain * OVERSAMPLE)

    for markets in event_candidates(tag):
        for c in markets[:MAX_PER_EVENT]:
            if c["market_id"] not in seen_markets:
                seen_markets.add(c["market_id"])
                shortlist.append(c)
        if len(shortlist) >= target:
            break

    contracts: list[dict] = []
    prices: list[dict] = []
    n_empty = 0
    for c in shortlist:
        if len(contracts) >= per_domain:
            break
        rows = series_for(c)
        if not rows:  # unusable for correlation analysis
            n_empty += 1
            continue
        contracts.append(c)
        prices.extend(rows)

    n_events = len({c["event_id"] for c in contracts})
    print(f"{tag:9s} {len(contracts):4d}/{per_domain} contratti | {n_events} eventi | "
          f"{n_empty} scartati (serie prezzi vuota)")
    return contracts, prices


def _partial(domain: str, kind: str) -> Path:
    return RAW / f"_partial_{domain}.{kind}.jsonl"


def _dump(rows: list[dict], path: Path) -> None:
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as f:
        return [json.loads(line) for line in f]


def merge() -> None:
    """Fuse the per-domain checkpoints into the final dataset."""
    contracts: list[dict] = []
    prices: list[dict] = []
    for domain in DOMAINS:
        contracts.extend(_load(_partial(domain, "contracts")))
        prices.extend(_load(_partial(domain, "prices")))

    _dump(contracts, RAW / "contracts.jsonl")
    _dump(prices, RAW / "prices.jsonl")
    print(f"\n{len(contracts)} contratti -> {RAW/'contracts.jsonl'}")
    print(f"{len(prices)} snapshot di prezzo -> {RAW/'prices.jsonl'}")


def main(domains: tuple[str, ...] = DOMAINS) -> None:
    """Collect the given domains, checkpointing each one before moving on.

    Each domain is written to its own partial file so a long run can be split
    across invocations; already-collected domains are reloaded (not re-fetched)
    to keep the cross-domain market/event dedup honest.
    """
    RAW.mkdir(parents=True, exist_ok=True)
    seen_markets: set[str] = set()

    for domain in DOMAINS:  # reload checkpoints so cross-domain dedup carries over
        for c in _load(_partial(domain, "contracts")):
            seen_markets.add(c["market_id"])

    for domain in domains:
        if _load(_partial(domain, "contracts")):
            print(f"{domain:9s} gia' presente, skip")
            continue
        contracts, prices = collect(domain, seen_markets)
        _dump(contracts, _partial(domain, "contracts"))
        _dump(prices, _partial(domain, "prices"))

    merge()


if __name__ == "__main__":
    import sys

    args = tuple(a for a in sys.argv[1:] if a in DOMAINS)
    if "--merge" in sys.argv:
        merge()
    else:
        main(args or DOMAINS)
