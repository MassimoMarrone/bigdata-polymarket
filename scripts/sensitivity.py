"""Sensibilita' alla soglia del linking + bootstrap CI sul profilo lead/lag.

Due domande dall'audit del 17/07:
1. (A9) I risultati a valle dipendono in modo fragile dalla soglia 0.35, scelta
   sul campione del giudice (dove l'ottimo di kappa e' 0.40)? Si rifanno il
   profilo lead/lag e il Task 3 a soglia 0.30 / 0.35 / 0.40.
2. (A4) Il picco a offset 0 (r=0.14) contro i fianchi (0.066) regge a un
   intervallo di confidenza? Bootstrap sui contratti (unita' di campionamento:
   il contratto, non il giorno — i giorni dello stesso contratto sono correlati).

NON scrive nei parquet consegnati: monkeypatcha la soglia nei moduli e replica
le sole aggregazioni, salvando in data/processed/sensitivity.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))

import correlation  # noqa: E402
import predict  # noqa: E402

THRESHOLDS = (0.30, 0.35, 0.40)
N_BOOT = 2000


def leadlag_at(thr: float) -> tuple[dict, pd.DataFrame]:
    """Profilo aggregato {offset: r medio} e matrice per-contratto (per il bootstrap)."""
    correlation.THRESHOLD = thr
    df = correlation.daily()
    profiles = {}
    for mid, g in df.groupby("market_id"):
        if len(g) < correlation.MIN_DAYS or g["volume"].sum() < 20:
            continue
        g = g.reset_index(drop=True)
        profiles[mid] = correlation.offset_profile(g["price_move"], g["volume"])
    mat = pd.DataFrame(profiles).T  # righe = contratti, colonne = offset
    return mat.mean().to_dict(), mat


def task3_at(thr: float) -> dict:
    """AUC per feature set (LogReg, stessi fold di predict.py), senza scrivere file."""
    predict.THRESHOLD = thr
    df = predict.load()
    feats = predict.social_features(df)
    feats = feats[feats["n_posts"] >= predict.MIN_POSTS]
    prices = predict.price_features(feats["market_id"])
    data = (feats.merge(prices, on="market_id", how="inner")
                 .dropna(subset=["price_cutoff"])
                 .sort_values("resolution_date").reset_index(drop=True))
    social_cols = ["n_posts", "n_days", "posts_per_day", "growth", "eng_mean",
                   "eng_max", "eng_hi_frac", "views_mean", "followers_mean",
                   "sent_mean", "sent_var", "frac_pos", "frac_neg", "sent_trend"]
    price_cols = ["price_cutoff", "price_30d"]
    data[price_cols] = data[price_cols].fillna(0.5)
    y = data["y"].to_numpy()
    out = {"n_contracts": int(len(data))}
    for name, cols in [("social", social_cols), ("price", price_cols),
                       ("combined", social_cols + price_cols)]:
        r = predict.evaluate(data[cols].to_numpy(dtype=float), y, predict.lr)
        out[f"auc_{name}"] = round(r["auc_roc"], 3)
    return out


def bootstrap_ci(mat: pd.DataFrame, n_boot: int = N_BOOT, seed: int = 0) -> dict:
    """CI al 95% (percentile) su r(0) e sul contrasto picco - media dei fianchi."""
    rng = np.random.default_rng(seed)
    vals = mat.to_numpy()
    idx0 = list(mat.columns).index(0)
    idxf = [list(mat.columns).index(-1), list(mat.columns).index(1)]
    peaks, contrasts = [], []
    for _ in range(n_boot):
        take = rng.integers(0, len(vals), len(vals))
        m = np.nanmean(vals[take], axis=0)
        peaks.append(m[idx0])
        contrasts.append(m[idx0] - np.mean(m[idxf]))
    pct = lambda a: (round(float(np.percentile(a, 2.5)), 3),
                     round(float(np.percentile(a, 97.5)), 3))
    return {"n_contracts": int(len(mat)),
            "r_peak_ci95": pct(peaks), "peak_minus_flanks_ci95": pct(contrasts)}


def main() -> None:
    results = {"leadlag": {}, "task3": {}}
    for thr in THRESHOLDS:
        prof, mat = leadlag_at(thr)
        peak = max(prof, key=prof.get)
        results["leadlag"][str(thr)] = {
            "n_contracts": int(len(mat)), "peak_offset": int(peak),
            "r_peak": round(prof[peak], 3),
            "flank_-1": round(prof[-1], 3), "flank_+1": round(prof[1], 3)}
        if thr == 0.35:
            results["bootstrap"] = bootstrap_ci(mat)
        results["task3"][str(thr)] = task3_at(thr)
        print(f"thr={thr}: leadlag {results['leadlag'][str(thr)]} | "
              f"task3 {results['task3'][str(thr)]}", flush=True)

    out = ROOT / "data" / "processed" / "sensitivity.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nbootstrap (thr 0.35): {results['bootstrap']}")
    print(f"salvato -> {out}")


if __name__ == "__main__":
    main()
