"""Normalise the raw JSONL into Parquet, and expose it through DuckDB.

Why Parquet + DuckDB (the brief asks us to motivate this):

- The raw layer stays JSONL: append-only, schema-free, immutable — it absorbs the
  fact that Bluesky and Telegram return different shapes, and it survives a killed
  collector without corrupting anything.
- The analytical layer is columnar because every question we ask is columnar: price
  series over time, post volume per day, sentiment per domain. Parquet stores each
  column separately, so scanning 85k price rows for one contract touches a fraction
  of the file, and it compresses time-series columns hard (repeated timestamps,
  low-cardinality categories).
- DuckDB queries those Parquet files in place, with no server and no import step.
  The dashboard opens the same files the pipeline wrote. For a single-machine
  dataset of this size that is strictly simpler than Postgres or Mongo, and much
  faster than pandas for the group-bys the dashboard needs on every interaction.

Platform schemas are unified here: a Bluesky post and a Telegram message become
rows of one `posts` table, with NULLs where a platform has no equivalent field
(Telegram has views, Bluesky does not; Bluesky has an author per post, a Telegram
channel is the author). Keeping them in one table is what makes the cross-platform
comparison a GROUP BY instead of a join.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"

MIN_SNAPSHOTS = 10  # a contract with 2 price points cannot support a lead/lag analysis


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.DataFrame([json.loads(line) for line in path.open()])


def contracts() -> pd.DataFrame:
    df = _read(RAW / "polymarket" / "contracts.jsonl")
    for col in ("creation_date", "close_date", "resolution_date"):
        df[col] = pd.to_datetime(df[col], format="mixed", utc=True)
    df["duration_days"] = (df["close_date"] - df["creation_date"]).dt.days
    df["outcomes"] = df["outcomes"].apply(json.dumps)
    df["is_binary"] = df["outcomes"].str.contains('"Yes"')
    return df.drop(columns=["clob_token_ids"])


def prices() -> pd.DataFrame:
    df = _read(RAW / "polymarket" / "prices.jsonl")
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    return df


def posts() -> pd.DataFrame:
    """Bluesky posts and Telegram messages, unified into one table."""
    frames = []
    bsky = _read(RAW / "bluesky" / "posts.jsonl")
    if not bsky.empty:
        bsky["hashtags"] = bsky["hashtags"].apply(json.dumps)
        frames.append(bsky)
    # Use the LINKED Telegram file (one row per post-contract pair, market_id set),
    # not the raw messages: posts.parquet must carry the same (post_id, market_id)
    # keys the linking scores use, or the two never join.
    tg = _read(RAW / "telegram" / "linked.jsonl")
    if not tg.empty:
        tg["hashtags"] = "[]"
        frames.append(tg)
    # Reddit: come Bluesky, i post portano gia' market_id (linked in reddit_scrapfly.py)
    rdt = _read(RAW / "reddit" / "posts.jsonl")
    if not rdt.empty:
        rdt["hashtags"] = rdt["hashtags"].apply(
            lambda h: json.dumps(h) if not isinstance(h, str) else h)
        frames.append(rdt)
    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df["published_at"] = pd.to_datetime(df["published_at"], format="mixed",
                                        utc=True, errors="coerce")
    df = df.dropna(subset=["published_at"])
    # One row per (post, contract): a post legitimately links to several contracts
    # ("Man City win the Champions League?" and "Inter win?" share the same posts),
    # so the identity of a row is the pair, not the post.
    df = df.drop_duplicates(subset=["post_id", "market_id"])
    df["text"] = df["text"].fillna("").str.strip()
    return _extra_fields(df[df["text"].str.len() > 0])


def _extra_fields(df: pd.DataFrame) -> pd.DataFrame:
    """The schema fields collected in a second pass (bluesky_extra.py) plus NER.

    All three joins are optional and per-POST (not per-pair): followers belong to
    the author, entities and comments to the post. Missing file -> NULL column,
    so the pipeline runs at any stage of the collection.
    """
    ent = _read(RAW.parent / "processed" / "post_enriched.jsonl")
    if not ent.empty:
        ent = ent[["post_id", "entities"]].rename(columns={"entities": "mentioned_entities"})
        ent["mentioned_entities"] = ent["mentioned_entities"].apply(json.dumps)
        df = df.merge(ent.drop_duplicates("post_id"), on="post_id", how="left")
    else:
        df["mentioned_entities"] = None

    aframes = [_read(RAW / "bluesky" / "authors.jsonl"),
               _read(RAW / "reddit" / "authors.jsonl")]
    aframes = [a[["author_id", "author_followers"]] for a in aframes if not a.empty]
    authors = pd.concat(aframes, ignore_index=True) if aframes else pd.DataFrame()
    if not authors.empty:
        df = df.merge(authors.dropna(subset=["author_id"]).drop_duplicates("author_id"),
                      on="author_id", how="left")
    else:
        df["author_followers"] = None

    # Commenti di entrambe le piattaforme che li espongono (Bluesky + Reddit),
    # stessa forma (parent_post_id, text, author_id, published_at, like_count).
    cframes = [_read(RAW / "bluesky" / "comments.jsonl"),
               _read(RAW / "reddit" / "comments.jsonl")]
    cframes = [c for c in cframes if not c.empty]
    comments = pd.concat(cframes, ignore_index=True) if cframes else pd.DataFrame()
    if not comments.empty:
        comments = comments[comments["text"].fillna("") != ""]
        sample = (comments.groupby("parent_post_id")
                  .apply(lambda g: json.dumps(g[["text", "author_id", "published_at",
                                                 "like_count"]].to_dict("records")),
                         include_groups=False)
                  .rename("comments").reset_index()
                  .rename(columns={"parent_post_id": "post_id"}))
        df = df.merge(sample, on="post_id", how="left")
    else:
        df["comments"] = None
    return df


def main() -> None:
    PROC.mkdir(parents=True, exist_ok=True)

    c, p = contracts(), prices()
    n_snap = p.groupby("market_id").size()
    usable = n_snap[n_snap >= MIN_SNAPSHOTS].index
    dropped = len(c) - c["market_id"].isin(usable).sum()
    c = c[c["market_id"].isin(usable)]
    p = p[p["market_id"].isin(usable)]

    c.to_parquet(PROC / "contracts.parquet", index=False)
    p.to_parquet(PROC / "prices.parquet", index=False)
    print(f"contratti: {len(c)} ({dropped} scartati: meno di {MIN_SNAPSHOTS} snapshot)")
    print(f"prezzi:    {len(p)}")
    print("per dominio:", c["category"].value_counts().to_dict())

    po = posts()
    if not po.empty:
        po.to_parquet(PROC / "posts.parquet", index=False)
        print(f"post:      {len(po)}")
        print("per piattaforma:", po["platform"].value_counts().to_dict())


if __name__ == "__main__":
    main()
