"""Lead/lag SCOMPOSTO per piattaforma (estende correlation.py, che aggrega).

Domanda: le tre piattaforme reagiscono al mercato allo stesso modo, o il *tipo*
di piattaforma (discussione utenti vs broadcast di notizie) cambia il profilo
temporale? Correla |Δprezzo| giornaliero col volume di post di ciascuna
piattaforma, sfasando ±7 giorni. Output: leadlag_platform.parquet.

Nota di lettura onesta: i segnali sono deboli (r ~0.05-0.08). Le differenze fra
piattaforme sono suggestive, non forti — da presentare come osservazione.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

PROC = Path(__file__).resolve().parents[1] / "data" / "processed"
THRESHOLD = 0.35
MAX_LAG = 7
MIN_DAYS = 10


def daily() -> pd.DataFrame:
    con = duckdb.connect()
    return con.execute(f"""
        WITH linked AS (
          SELECT p.market_id, p.platform, date_trunc('day', p.published_at) AS d
          FROM read_parquet('{PROC/'posts.parquet'}') p
          JOIN read_json_auto('{PROC/'post_scores.jsonl'}') s
               ON p.post_id=s.post_id AND p.market_id=s.market_id
          WHERE s.sim_mpnet >= {THRESHOLD}),
        vol AS (SELECT market_id, platform, d, count(*) AS n FROM linked GROUP BY 1,2,3),
        pr AS (SELECT market_id, date_trunc('day', timestamp) AS d, avg(price) AS px
               FROM read_parquet('{PROC/'prices.parquet'}') WHERE outcome='Yes' GROUP BY 1,2)
        SELECT v.market_id, v.platform, v.d, v.n, p.px
        FROM vol v JOIN pr p USING (market_id, d)
    """).df()


def xcorr(g: pd.DataFrame, lag: int) -> float:
    dp = g["px"].diff().abs()
    v = g["n"].shift(lag)                 # lag>0: volume dopo il movimento -> insegue
    m = dp.notna() & v.notna()
    if m.sum() < 8 or dp[m].std() == 0 or v[m].std() == 0:
        return np.nan
    return float(np.corrcoef(dp[m], v[m])[0, 1])


def main() -> None:
    df = daily()
    rows = []
    for plat in ("reddit", "bluesky", "telegram"):
        sub = df[df.platform == plat]
        for lag in range(-MAX_LAG, MAX_LAG + 1):
            rs = [xcorr(g.sort_values("d"), lag)
                  for _, g in sub.groupby("market_id") if len(g) >= MIN_DAYS]
            rs = [r for r in rs if not np.isnan(r)]
            rows.append({"platform": plat, "lag": lag,
                         "r": float(np.mean(rs)) if rs else np.nan,
                         "n_contracts": len(rs)})
    out = pd.DataFrame(rows)
    out.to_parquet(PROC / "leadlag_platform.parquet", index=False)

    print("Picco di correlazione per piattaforma (lag>0 = insegue il mercato):")
    for plat in ("reddit", "bluesky", "telegram"):
        s = out[out.platform == plat].dropna(subset=["r"])
        peak = s.loc[s["r"].idxmax()]
        print(f"  {plat:9s} picco a lag {int(peak['lag']):+d} (r={peak['r']:+.3f})")
    print(f"\nsalvato -> {PROC/'leadlag_platform.parquet'}")


if __name__ == "__main__":
    main()
