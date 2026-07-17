"""Direction analysis: is the SIGN of sentiment aligned with the SIGN of price moves?

The brief asks explicitly "whether the direction of sentiment is aligned with the
direction of price change" and whether "rapid shifts in aggregate sentiment are
temporally correlated with significant movements". correlation.py answers the volume
question (|dP| ~ volume); this module answers the sentiment ones, three ways:

1. **Signed lead/lag** — r(dP, mean sentiment) shifting sentiment by -7..+7 days.
2. **Alignment on big-move days** — on the days a contract really moved (top decile
   of |dP| within the contract), does sentiment sign agree with the price direction
   more often than a coin flip? Binomial test against 0.5.
3. **Sentiment shifts vs big moves** — r(|d(sentiment)|, |dP|) per lag: rapid shifts
   in aggregate sentiment against significant price movements, direction-free.

A methodological caveat worth stating in the report: sentiment polarity is about the
*topic*, not about the "Yes" outcome. "Will Iran strike Israel?" rising is *bad* news,
so negative sentiment accompanies a price INCREASE. Alignment can therefore be weak or
even inverted per contract without the pipeline being wrong; measuring it honestly is
the point.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from correlation import MAX_LAG, MIN_DAYS, daily, xcorr

PROC = Path(__file__).resolve().parents[1] / "data" / "processed"
BIG_MOVE_Q = 0.90  # a "significant" day = top decile of |dP| within the contract
MIN_POSTS = 20     # same eligibility bar as correlation.py


def eligible(df: pd.DataFrame) -> pd.DataFrame:
    """Contracts with enough days AND enough sentiment-bearing posts."""
    ok = []
    for mid, g in df.groupby("market_id"):
        if len(g) >= MIN_DAYS and g["volume"].sum() >= MIN_POSTS:
            ok.append(mid)
    return df[df["market_id"].isin(ok)]


def leadlag_signed(df: pd.DataFrame, contracts: pd.DataFrame) -> pd.DataFrame:
    """Analyses 1 and 3: per-contract lead/lag on signed and shift series."""
    rows = []
    for mid, g in df.groupby("market_id"):
        g = g.reset_index(drop=True)
        # d(sentiment): only meaningful on days that HAVE posts; a 0-filled day is
        # "no data", not "neutral crowd" -> mask empty days before differencing.
        sent = g["sentiment"].where(g["volume"] > 0)
        sent_shift = sent.diff().abs()
        # Stessa convenzione di correlation.offset_profile: lag = offset di
        # calendario (giorno del sentiment - giorno del movimento), col -1 dei
        # timestamp midnight incorporato. Il risultato qui e' un nullo piatto,
        # simmetrico per costruzione, ma le etichette devono comunque dire il vero.
        for off in range(-MAX_LAG, MAX_LAG + 1):
            rows.append({
                "market_id": mid, "lag": off,
                "r_signed": xcorr(g["price_delta"], sent, 1 - off),
                "r_shift": xcorr(g["price_move"], sent_shift, 1 - off),
            })
    return pd.DataFrame(rows).merge(contracts, on="market_id")


def alignment_big_days(df: pd.DataFrame) -> dict:
    """Analysis 2: sign agreement between sentiment and dP on big-move days."""
    out = {}
    for scope, g in [("tutti", df)] + list(df.groupby("category")):
        big = []
        for mid, gc in g.groupby("market_id"):
            thr = gc["price_move"].quantile(BIG_MOVE_Q)
            sel = gc[(gc["price_move"] >= thr) & (gc["volume"] > 0)
                     & (gc["sentiment"] != 0)]
            big.append(sel)
        big = pd.concat(big) if big else pd.DataFrame()
        if big.empty:
            continue
        agree = int((np.sign(big["sentiment"]) == np.sign(big["price_delta"])).sum())
        n = len(big)
        p = stats.binomtest(agree, n, 0.5).pvalue
        out[scope] = {"giorni": n, "allineati": agree,
                      "rate": agree / n, "p_value": p}
    return out


def main() -> None:
    contracts = pd.read_parquet(PROC / "contracts.parquet",
                                columns=["market_id", "category", "question"])
    df = eligible(daily()).merge(contracts[["market_id", "category"]], on="market_id")
    res = leadlag_signed(df, contracts)
    res.to_parquet(PROC / "sentiment_direction.parquet", index=False)
    n = res["market_id"].nunique()
    print(f"{n} contratti eleggibili (>= {MIN_DAYS} giorni, >= {MIN_POSTS} post)\n")

    for col, label in [("r_signed", "SENTIMENT firmato ~ dP firmato"),
                       ("r_shift", "|shift sentiment| ~ |dP| (traccia: 'rapid shifts')")]:
        agg = res.groupby("lag")[col].mean()
        peak = agg.abs().idxmax()
        print(f"Correlazione media {label}:")
        for lag, r in agg.items():
            bar = "#" * int(abs(r) * 300)
            print(f"  lag {lag:+2d} gg  r={r:+.3f}  {bar}"
                  f"{'  <<< PICCO' if lag == peak else ''}")
        print(f"  -> picco a lag {peak:+d} (r={agg[peak]:+.3f})\n")

    print(f"Allineamento di direzione nei giorni di grande movimento "
          f"(top {int((1-BIG_MOVE_Q)*100)}% |dP| del contratto, baseline 50%):")
    for scope, a in alignment_big_days(df).items():
        sig = "significativo" if a["p_value"] < 0.05 else "NON significativo"
        print(f"  {scope:9s} {a['allineati']}/{a['giorni']} = {a['rate']:.1%} "
              f"(p={a['p_value']:.3f}, {sig})")

    print("\nPer dominio, picco r_signed:")
    for dom, g in res.groupby("category"):
        a = g.groupby("lag")["r_signed"].mean()
        peak = a.abs().idxmax()
        print(f"  {dom:9s} lag {peak:+d} gg (r={a[peak]:+.3f})")


if __name__ == "__main__":
    main()
