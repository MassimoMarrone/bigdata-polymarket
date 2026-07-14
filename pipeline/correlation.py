"""Lead/lag between social discourse and Polymarket prices — the central analysis.

The question is not "does social volume correlate with price" (levels correlate for
trivial reasons: a busy contract is a busy topic). It is: **when the market changes
its mind, had the crowd moved first?** So we correlate *changes*, not levels — daily
price movement against daily social activity — and we shift one series against the
other by -7..+7 days.

Reading the result:
  lag < 0  -> social leads: the spike came BEFORE the price moved (social is informative)
  lag = 0  -> they move together (both react to the same news)
  lag > 0  -> social follows: the crowd is commenting on a move that already happened

Only the semantic-filtered links count (MPNet >= THRESHOLD, calibrated against the
LLM judge at kappa=0.434): unfiltered keyword hits carry ~31% noise of the
"same entity, wrong question" kind, which would blur exactly the signal we are after.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"

THRESHOLD = 0.35  # MPNet cosine; see Decisioni.md
MAX_LAG = 7
MIN_DAYS = 20  # a lead/lag estimate on a handful of days is noise


def links() -> pd.DataFrame:
    """(post, contract) pairs that survive the semantic filter."""
    scores = pd.DataFrame([json.loads(l) for l in (PROC / "post_scores.jsonl").open()])
    return scores[scores["sim_mpnet"] >= THRESHOLD][["post_id", "market_id"]]


def daily() -> pd.DataFrame:
    """Per contract-day: price move, post volume, mean sentiment."""
    posts = pd.read_parquet(PROC / "posts.parquet",
                            columns=["post_id", "market_id", "published_at"])
    enr = pd.DataFrame([json.loads(l) for l in (PROC / "post_enriched.jsonl").open()])
    kept = links()

    posts = (posts.merge(kept, on=["post_id", "market_id"])
                  .merge(enr[["post_id", "sentiment_score", "language"]], on="post_id",
                         how="left"))
    posts = posts[posts["language"] == "en"]
    posts["day"] = posts["published_at"].dt.floor("D")

    social = (posts.groupby(["market_id", "day"])
                   .agg(volume=("post_id", "count"),
                        sentiment=("sentiment_score", "mean"))
                   .reset_index())

    prices = pd.read_parquet(PROC / "prices.parquet")
    prices = prices[prices["outcome"].isin(["Yes", "Over"])].copy()
    prices["day"] = prices["timestamp"].dt.floor("D")
    price = (prices.groupby(["market_id", "day"])["price"].mean().reset_index())

    df = price.merge(social, on=["market_id", "day"], how="left")
    df[["volume", "sentiment"]] = df[["volume", "sentiment"]].fillna(0)
    df = df.sort_values(["market_id", "day"])
    # Changes, not levels. Keep the SIGNED delta too: the direction analysis
    # (sentiment_direction.py) needs to know which way the market moved.
    df["price_delta"] = df.groupby("market_id")["price"].diff()
    df["price_move"] = df["price_delta"].abs()
    return df.dropna(subset=["price_move"])


def xcorr(a: pd.Series, b: pd.Series, lag: int) -> float:
    """Correlation between a and b with b shifted by `lag` days (lag<0: b leads)."""
    shifted = b.shift(lag)
    mask = shifted.notna() & a.notna()
    if mask.sum() < MIN_DAYS or a[mask].std() == 0 or shifted[mask].std() == 0:
        return np.nan
    return float(np.corrcoef(a[mask], shifted[mask])[0, 1])


def main() -> None:
    df = daily()
    contracts = pd.read_parquet(PROC / "contracts.parquet",
                                columns=["market_id", "category", "question"])

    rows = []
    for mid, g in df.groupby("market_id"):
        if len(g) < MIN_DAYS or g["volume"].sum() < 20:
            continue
        g = g.reset_index(drop=True)
        for lag in range(-MAX_LAG, MAX_LAG + 1):
            rows.append({
                "market_id": mid, "lag": lag,
                "r_volume": xcorr(g["price_move"], g["volume"], lag),
                "r_sentiment": xcorr(g["price_move"], g["sentiment"], lag),
            })
    res = pd.DataFrame(rows).merge(contracts, on="market_id")
    res.to_parquet(PROC / "leadlag.parquet", index=False)

    n = res["market_id"].nunique()
    print(f"{n} contratti con abbastanza dati (>= {MIN_DAYS} giorni, >= 20 post)\n")

    print("Correlazione media |variazione prezzo| ~ volume social, per sfasamento:")
    print("  (lag<0 = i social ANTICIPANO | lag>0 = i social INSEGUONO)\n")
    agg = res.groupby("lag")["r_volume"].mean()
    peak = agg.idxmax()
    for lag, r in agg.items():
        bar = "#" * int(max(0, r) * 200)
        star = "  <<< PICCO" if lag == peak else ""
        print(f"  lag {lag:+2d} gg  r={r:+.3f}  {bar}{star}")

    print(f"\nPicco a lag {peak:+d} -> ", end="")
    if peak < 0:
        print("i social ANTICIPANO il movimento di prezzo")
    elif peak == 0:
        print("social e mercato si muovono INSIEME (reagiscono alla stessa notizia)")
    else:
        print("i social INSEGUONO il movimento di prezzo")

    print("\nPer dominio:")
    for dom, g in res.groupby("category"):
        a = g.groupby("lag")["r_volume"].mean()
        print(f"  {dom:9s} picco a lag {a.idxmax():+d} gg (r={a.max():+.3f})")


if __name__ == "__main__":
    main()
