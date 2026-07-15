"""Task 3 (optional) — Outcome prediction from social media features.

Research question (from the brief): does social discourse — independently of, or in
combination with, the market price — carry statistically useful information for
forecasting the resolution outcome of a contract?

Design choices that keep the experiment honest:

- **Cutoff at 7 days before resolution.** Every feature (social AND price) is computed
  only on data published up to `resolution_date - 7d`. Posts written while the outcome
  is already de-facto known would leak the label ("Trump nominated X" the day after
  the nomination). 7 days matches the §7.1 analysis window of the report.
- **Three feature sets, same contracts, same folds**: SOCIAL only, PRICE only
  (last "Yes" price before cutoff + 30d before), COMBINED. Given §7.1 (markets are
  calibrated months ahead) the pre-registered expectation is price >> social; the
  interesting number is whether COMBINED beats PRICE at all.
- **Temporal cross-validation**: contracts sorted by resolution_date, walk-forward
  expanding window (sklearn TimeSeriesSplit, 5 folds): the model always predicts
  contracts that resolve AFTER everything it was trained on. No random shuffling.
- **Binary contracts only** (Yes/No — 366/378), majority-class baseline reported.

Outputs: printed table + data/processed/prediction_results.json (for the report).
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

PROC = Path(__file__).resolve().parents[1] / "data" / "processed"
THRESHOLD = 0.35   # same semantic filter as the dashboard
CUTOFF_DAYS = 7    # features stop 7 days before resolution
MIN_POSTS = 5      # a contract enters the dataset with >=5 pre-cutoff posts
N_SPLITS = 5


def load() -> pd.DataFrame:
    con = duckdb.connect()
    df = con.execute(f"""
        WITH linked AS (
            SELECT p.market_id, p.published_at, p.text,
                   p.like_count + p.reply_count + p.repost_count AS engagement,
                   coalesce(p.view_count, 0) AS views,
                   coalesce(p.author_followers, 0) AS followers,
                   e.sentiment, e.sentiment_score,
                   c.resolution_outcome, c.resolution_date, c.category
            FROM read_parquet('{PROC / "posts.parquet"}') p
            JOIN read_json_auto('{PROC / "post_scores.jsonl"}') s
                 ON p.post_id = s.post_id AND p.market_id = s.market_id
            JOIN read_parquet('{PROC / "contracts.parquet"}') c
                 ON p.market_id = c.market_id
            LEFT JOIN read_json_auto('{PROC / "post_enriched.jsonl"}') e
                 ON p.post_id = e.post_id
            WHERE s.sim_mpnet >= {THRESHOLD}
              AND c.resolution_outcome IN ('Yes', 'No')
              AND p.published_at < c.resolution_date - INTERVAL {CUTOFF_DAYS} DAY
        )
        SELECT * FROM linked
    """).df()
    return df


def social_features(df: pd.DataFrame) -> pd.DataFrame:
    """One row per contract: volume, engagement, sentiment feature blocks."""
    rows = []
    for mid, g in df.groupby("market_id"):
        g = g.sort_values("published_at")
        days = (g["published_at"].dt.normalize().nunique()) or 1
        # growth: posts in the last third of the active window vs the first third
        t0, t1 = g["published_at"].min(), g["published_at"].max()
        span = (t1 - t0) or pd.Timedelta(days=1)
        early = (g["published_at"] < t0 + span / 3).sum()
        late = (g["published_at"] > t1 - span / 3).sum()
        sent = g["sentiment_score"].dropna()
        half = len(sent) // 2
        eng = g["engagement"].fillna(0)
        rows.append({
            "market_id": mid,
            "resolution_date": g["resolution_date"].iloc[0],
            "y": int(g["resolution_outcome"].iloc[0] == "Yes"),
            # volume
            "n_posts": len(g), "n_days": days,
            "posts_per_day": len(g) / days,
            "growth": (late + 1) / (early + 1),
            # engagement
            "eng_mean": eng.mean(), "eng_max": eng.max(),
            "eng_hi_frac": (eng > eng.quantile(0.9)).mean() if len(g) > 10 else 0.0,
            "views_mean": g["views"].mean(),
            "followers_mean": g["followers"].mean(),
            # sentiment
            "sent_mean": sent.mean() if len(sent) else 0.0,
            "sent_var": sent.var() if len(sent) > 1 else 0.0,
            "frac_pos": (g["sentiment"] == "positive").mean(),
            "frac_neg": (g["sentiment"] == "negative").mean(),
            "sent_trend": (sent.iloc[half:].mean() - sent.iloc[:half].mean())
                          if len(sent) > 3 else 0.0,
        })
    return pd.DataFrame(rows).fillna(0.0)


def price_features(mids: pd.Series) -> pd.DataFrame:
    """Last 'Yes' price before the same cutoff, and 30 days before resolution."""
    con = duckdb.connect()
    q = f"""
        SELECT pr.market_id,
               arg_max(pr.price, pr.timestamp) FILTER (
                   pr.timestamp < c.resolution_date - INTERVAL {CUTOFF_DAYS} DAY
               ) AS price_cutoff,
               arg_max(pr.price, pr.timestamp) FILTER (
                   pr.timestamp < c.resolution_date - INTERVAL 30 DAY
               ) AS price_30d
        FROM read_parquet('{PROC / "prices.parquet"}') pr
        JOIN read_parquet('{PROC / "contracts.parquet"}') c
             ON pr.market_id = c.market_id
        WHERE pr.outcome = 'Yes'
        GROUP BY pr.market_id
    """
    p = con.execute(q).df()
    return p[p["market_id"].isin(mids)]


def texts_per_contract(df: pd.DataFrame) -> pd.Series:
    return df.groupby("market_id")["text"].apply(lambda t: " ".join(t.astype(str)))


def evaluate(X: np.ndarray, y: np.ndarray, model) -> dict:
    """Walk-forward CV on chronologically sorted contracts."""
    accs, f1s, aucs = [], [], []
    for tr, te in TimeSeriesSplit(n_splits=N_SPLITS).split(X):
        m = model()
        m.fit(X[tr], y[tr])
        pred = m.predict(X[te])
        accs.append(accuracy_score(y[te], pred))
        f1s.append(f1_score(y[te], pred, average="macro"))
        if len(np.unique(y[te])) > 1:
            proba = m.predict_proba(X[te])[:, 1]
            aucs.append(roc_auc_score(y[te], proba))
    return {"accuracy": float(np.mean(accs)), "macro_f1": float(np.mean(f1s)),
            "auc_roc": float(np.mean(aucs)) if aucs else float("nan"),
            "acc_std": float(np.std(accs))}


def lr():
    return make_pipeline(StandardScaler(),
                         LogisticRegression(max_iter=2000, class_weight="balanced"))


def gb():
    return HistGradientBoostingClassifier(max_iter=200, random_state=0)


def main() -> None:
    df = load()
    feats = social_features(df)
    feats = feats[feats["n_posts"] >= MIN_POSTS]
    prices = price_features(feats["market_id"])
    data = feats.merge(prices, on="market_id", how="inner").dropna(
        subset=["price_cutoff"]).sort_values("resolution_date").reset_index(drop=True)

    social_cols = ["n_posts", "n_days", "posts_per_day", "growth", "eng_mean",
                   "eng_max", "eng_hi_frac", "views_mean", "followers_mean",
                   "sent_mean", "sent_var", "frac_pos", "frac_neg", "sent_trend"]
    price_cols = ["price_cutoff", "price_30d"]
    data[price_cols] = data[price_cols].fillna(0.5)  # no series that early = max uncertainty
    y = data["y"].to_numpy()

    print(f"{len(data)} contratti eleggibili (>= {MIN_POSTS} post pre-cutoff, "
          f"cutoff {CUTOFF_DAYS}gg), Yes = {y.mean():.1%}")
    results = {"n_contracts": len(data), "yes_rate": float(y.mean()),
               "majority_baseline_acc": float(max(y.mean(), 1 - y.mean())),
               "cutoff_days": CUTOFF_DAYS, "sets": {}}

    for name, cols in [("social", social_cols), ("price", price_cols),
                       ("combined", social_cols + price_cols)]:
        X = data[cols].to_numpy(dtype=float)
        for mname, mk in [("logreg", lr), ("gboost", gb)]:
            r = evaluate(X, y, mk)
            results["sets"][f"{name}/{mname}"] = r
            print(f"  {name:9s} {mname:7s} acc={r['accuracy']:.3f}±{r['acc_std']:.3f} "
                  f"macroF1={r['macro_f1']:.3f} AUC={r['auc_roc']:.3f}")

    # linguistic features (TF-IDF of the contract's linked posts), fit per fold
    texts = texts_per_contract(df)
    data["text"] = data["market_id"].map(texts).fillna("")
    accs, f1s, aucs = [], [], []
    for tr, te in TimeSeriesSplit(n_splits=N_SPLITS).split(data):
        vec = TfidfVectorizer(max_features=300, stop_words="english", min_df=3)
        Xtr = vec.fit_transform(data["text"].iloc[tr])
        Xte = vec.transform(data["text"].iloc[te])
        m = LogisticRegression(max_iter=2000, class_weight="balanced")
        m.fit(Xtr, y[tr])
        pred = m.predict(Xte)
        accs.append(accuracy_score(y[te], pred))
        f1s.append(f1_score(y[te], pred, average="macro"))
        if len(np.unique(y[te])) > 1:
            aucs.append(roc_auc_score(y[te], m.predict_proba(Xte)[:, 1]))
    r = {"accuracy": float(np.mean(accs)), "macro_f1": float(np.mean(f1s)),
         "auc_roc": float(np.mean(aucs)) if aucs else float("nan"),
         "acc_std": float(np.std(accs))}
    results["sets"]["linguistic/tfidf-logreg"] = r
    print(f"  {'linguist.':9s} {'tfidf':7s} acc={r['accuracy']:.3f}±{r['acc_std']:.3f} "
          f"macroF1={r['macro_f1']:.3f} AUC={r['auc_roc']:.3f}")

    out = PROC / "prediction_results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nbaseline maggioranza: acc={results['majority_baseline_acc']:.3f}")
    print(f"salvato -> {out}")


if __name__ == "__main__":
    main()
