"""Lead/lag between social discourse and Polymarket prices — the central analysis.

The question is not "does social volume correlate with price" (levels correlate for
trivial reasons: a busy contract is a busy topic). It is: **when the market changes
its mind, had the crowd moved first?** So we correlate *changes*, not levels — daily
price movement against daily social activity — shifted by -7..+7 days.

Convention (fixed 2026-07-17, see tests/test_correlation.py):

  offset = day(volume) − day(price move)
  offset < 0  -> social leads: the spike came BEFORE the price moved
  offset = 0  -> same day (both react to the same news)
  offset > 0  -> social follows: the crowd comments on a move that already happened

Two timing subtleties that produced an inverted reading before the fix:

1. `Series.shift(k)[t] = series[t-k]`: a POSITIVE shift pairs today's move with
   PAST volume. The old code labeled that side "social follows" — backwards.
2. Price snapshots are daily points stamped at midnight UTC: the point stamped
   day t is the price at the t-1/t boundary, so diff(t) is the move that
   happened DURING day t-1. Day attribution must account for that extra -1.

Both are encoded in `offset_profile` and pinned by synthetic regression tests.
Residual honesty note: with midnight-stamped daily data the day attribution
rests on the boundary convention; the robust claim is at the granularity of
"same day vs ±1", not finer.

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


def xcorr(a: pd.Series, b: pd.Series, shift: int, min_days: int = MIN_DAYS) -> float:
    """Raw math: corr(a[t], b[t-shift]). Positive shift pairs a with PAST b.

    Do not call this directly for lead/lag questions — use `offset_profile`,
    which owns the calendar conventions. This is just aligned correlation.
    """
    shifted = b.shift(shift)
    mask = shifted.notna() & a.notna()
    if mask.sum() < min_days or a[mask].std() == 0 or shifted[mask].std() == 0:
        return np.nan
    return float(np.corrcoef(a[mask], shifted[mask])[0, 1])


def offset_profile(price_move: pd.Series, series: pd.Series,
                   max_lag: int = MAX_LAG, min_days: int = MIN_DAYS) -> dict[int, float]:
    """r per offset, where offset = day(series) − day(price move).

    price_move[t] is the |diff| of midnight-stamped snapshots, i.e. the move
    that happened during day t-1. The series value for day (t-1)+offset sits at
    row t-1+offset = t-(1-offset), which is series.shift(1-offset)[t]. Hence:

        r(offset) = corr(price_move[t], series[t-(1-offset)])

    Positional caveat: shift() moves by ROW; on gaps in the daily price series
    "1 row" can exceed "1 day". Daily snapshots are near-contiguous, so the
    approximation is small, but it is one more reason to read the profile at
    the granularity of "same day vs ±1", not finer.
    """
    return {off: xcorr(price_move, series, 1 - off, min_days)
            for off in range(-max_lag, max_lag + 1)}


def main() -> None:
    df = daily()
    contracts = pd.read_parquet(PROC / "contracts.parquet",
                                columns=["market_id", "category", "question"])

    rows = []
    for mid, g in df.groupby("market_id"):
        if len(g) < MIN_DAYS or g["volume"].sum() < 20:
            continue
        g = g.reset_index(drop=True)
        vol = offset_profile(g["price_move"], g["volume"])
        sen = offset_profile(g["price_move"], g["sentiment"])
        for off in vol:
            rows.append({"market_id": mid, "lag": off,
                         "r_volume": vol[off], "r_sentiment": sen[off]})
    res = pd.DataFrame(rows).merge(contracts, on="market_id")
    res.to_parquet(PROC / "leadlag.parquet", index=False)

    n = res["market_id"].nunique()
    print(f"{n} contratti con abbastanza dati (>= {MIN_DAYS} giorni, >= 20 post)\n")

    print("Correlazione media |variazione prezzo| ~ volume social, per offset:")
    print("  (offset = giorno del volume - giorno del movimento;")
    print("   <0 = i social ANTICIPANO | 0 = stesso giorno | >0 = INSEGUONO)\n")
    agg = res.groupby("lag")["r_volume"].mean()
    peak = agg.idxmax()
    for off, r in agg.items():
        bar = "#" * int(max(0, r) * 200)
        star = "  <<< PICCO" if off == peak else ""
        print(f"  offset {off:+2d} gg  r={r:+.3f}  {bar}{star}")

    print(f"\nPicco a offset {peak:+d} -> ", end="")
    if peak < 0:
        print("i social ANTICIPANO il movimento di prezzo")
    elif peak == 0:
        print("social e mercato si muovono lo STESSO GIORNO (co-movimento, nessun lead)")
    else:
        print("i social INSEGUONO il movimento di prezzo")

    print("\nPer dominio:")
    for dom, g in res.groupby("category"):
        a = g.groupby("lag")["r_volume"].mean()
        print(f"  {dom:9s} picco a lag {a.idxmax():+d} gg (r={a.max():+.3f})")


if __name__ == "__main__":
    main()
