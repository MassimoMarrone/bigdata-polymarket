"""Lead/lag SCOMPOSTO per piattaforma (estende correlation.py, che aggrega).

Domanda: le tre piattaforme mostrano lo stesso profilo temporale rispetto ai
movimenti di prezzo? Convenzione degli offset identica a correlation.py
(offset = giorno del volume - giorno del movimento; vedi tests/test_correlation.py
per la storia dell'inversione corretta il 2026-07-17).

Nota di lettura onesta: i segnali sono deboli (r ~0.05-0.14) e a granularita'
giornaliera con snapshot midnight-stamped NESSUNA differenza direzionale fra
piattaforme e' difendibile. Il valore del confronto e' su copertura e rumore
(Telegram sparso => profilo instabile), non sulla direzione.

MIN_DAYS=10 (non 20 come nell'aggregato): le serie per-piattaforma sono piu'
sparse — a 20 giorni minimi Telegram perderebbe quasi tutti i contratti e il
confronto a tre non esisterebbe. Soglia piu' permissiva = piu' rumore, ed e'
parte del motivo per cui questo file produce un'osservazione, non un risultato.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from correlation import offset_profile  # noqa: E402

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


def main() -> None:
    df = daily()
    rows = []
    for plat in ("reddit", "bluesky", "telegram"):
        sub = df[df.platform == plat]
        profiles = []
        for _, g in sub.groupby("market_id"):
            if len(g) < MIN_DAYS:
                continue
            g = g.sort_values("d").reset_index(drop=True)
            dp = g["px"].diff().abs()
            profiles.append(offset_profile(dp, g["n"], MAX_LAG, min_days=8))
        for off in range(-MAX_LAG, MAX_LAG + 1):
            rs = [p[off] for p in profiles if not np.isnan(p[off])]
            rows.append({"platform": plat, "lag": off,
                         "r": float(np.mean(rs)) if rs else np.nan,
                         "n_contracts": len(rs)})
    out = pd.DataFrame(rows)
    out.to_parquet(PROC / "leadlag_platform.parquet", index=False)

    print("Profilo per piattaforma (offset = giorno volume - giorno movimento):")
    for plat in ("reddit", "bluesky", "telegram"):
        s = out[out.platform == plat].dropna(subset=["r"])
        peak = s.loc[s["r"].idxmax()]
        print(f"  {plat:9s} picco a offset {int(peak['lag']):+d} (r={peak['r']:+.3f}, "
              f"n={int(peak['n_contracts'])})")
    print(f"\nsalvato -> {PROC/'leadlag_platform.parquet'}")


if __name__ == "__main__":
    main()
