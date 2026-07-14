"""Fill the two schema fields the first Bluesky pass could not: comments and followers.

The brief's schema asks for "a sample of replies or comments associated with each
post" and for `author_followers` "where available". searchPosts returns neither, so
this is a second, targeted pass over the posts we actually kept (semantic filter):

- **Comments** — `app.bsky.feed.getPostThread` on the top posts per contract by
  engagement (a *sample*, as the brief says: fetching threads for 32k posts would
  be 32k calls for replies nobody analyses).
- **Followers** — `app.bsky.actor.getProfiles` (batch of 25) over the unique
  authors of kept posts.

Both outputs are raw-layer JSONL, append-only, resumable like every collector here.
Telegram has no equivalent: broadcast channels expose views but neither public
comment threads (without joining linked discussion groups) nor a followers notion
per author — the channel IS the author. Documented as a platform limit.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from bluesky import RAW, UA, _env, login, _headers  # riusa auth e path

API = "https://api.bsky.app/xrpc"
PROC = Path(__file__).resolve().parents[1] / "data" / "processed"
COMMENTS = RAW / "bluesky" / "comments.jsonl"
AUTHORS = RAW / "bluesky" / "authors.jsonl"

THRESHOLD = 0.35        # same filter as every analysis (Decisioni.md)
TOP_PER_CONTRACT = 5    # posts per contract whose thread we sample
MAX_REPLIES = 20        # replies kept per post (a sample, not the full thread)


def _get(endpoint: str, params: dict, retries: int = 4) -> dict:
    for attempt in range(retries):
        try:
            r = requests.get(f"{API}/{endpoint}", params=params,
                             headers=_headers(), timeout=45)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.status_code in (429,) or r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        if r.status_code in (400, 403, 404):
            return {}  # gone/blocked post or profile: skip, don't die
        r.raise_for_status()
        return r.json()
    return {}


def kept_posts() -> pd.DataFrame:
    """Bluesky (post, contract) pairs that survive the semantic filter."""
    scores = pd.DataFrame([json.loads(l) for l in (PROC / "post_scores.jsonl").open()])
    posts = pd.read_parquet(PROC / "posts.parquet",
                            columns=["post_id", "market_id", "platform", "author_id",
                                     "like_count", "reply_count", "repost_count"])
    df = posts[posts["platform"] == "bluesky"].merge(
        scores[scores["sim_mpnet"] >= THRESHOLD][["post_id", "market_id"]],
        on=["post_id", "market_id"])
    df["engagement"] = df[["like_count", "reply_count", "repost_count"]].sum(axis=1)
    return df


def _done(path: Path, key: str) -> set[str]:
    if not path.exists():
        return set()
    return {json.loads(line)[key] for line in path.open()}


def collect_comments(df: pd.DataFrame) -> None:
    """Sample of replies for the top posts per contract that have any."""
    top = (df[df["reply_count"] > 0]
           .sort_values("engagement", ascending=False)
           .groupby("market_id").head(TOP_PER_CONTRACT))
    targets = top.drop_duplicates("post_id")
    done = _done(COMMENTS, "parent_post_id")
    todo = targets[~targets["post_id"].isin(done)]
    print(f"commenti: {len(targets)} post target, {len(todo)} da fare", flush=True)

    n = 0
    with COMMENTS.open("a") as f:
        for i, row in enumerate(todo.itertuples(), 1):
            data = _get("app.bsky.feed.getPostThread",
                        {"uri": row.post_id, "depth": 1})
            replies = (data.get("thread") or {}).get("replies") or []
            wrote = False
            for rep in replies[:MAX_REPLIES]:
                p = rep.get("post") or {}
                rec = p.get("record", {})
                author = p.get("author", {})
                f.write(json.dumps({
                    "comment_id": p.get("uri"),
                    "parent_post_id": row.post_id,
                    "platform": "bluesky",
                    "text": rec.get("text", ""),
                    "author_id": author.get("did"),
                    "author_name": author.get("displayName") or author.get("handle"),
                    "published_at": rec.get("createdAt"),
                    "like_count": p.get("likeCount", 0),
                    "reply_count": p.get("replyCount", 0),
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                }) + "\n")
                n += 1
                wrote = True
            if not wrote:  # thread gone or empty: mark done so resume skips it
                f.write(json.dumps({"comment_id": None, "parent_post_id": row.post_id,
                                    "platform": "bluesky", "text": ""}) + "\n")
            if i % 100 == 0:
                print(f"  commenti {i}/{len(todo)} post | {n} reply", flush=True)
            time.sleep(0.2)
    print(f"commenti: +{n} reply -> {COMMENTS}", flush=True)


def collect_followers(df: pd.DataFrame) -> None:
    """author_followers via getProfiles, 25 DIDs per call."""
    dids = sorted(set(df["author_id"].dropna()) - _done(AUTHORS, "author_id"))
    print(f"follower: {df['author_id'].nunique()} autori, {len(dids)} da fare", flush=True)

    n = 0
    with AUTHORS.open("a") as f:
        for i in range(0, len(dids), 25):
            batch = dids[i:i + 25]
            data = _get("app.bsky.actor.getProfiles", {"actors": batch})
            got = {p["did"]: p for p in data.get("profiles", [])}
            for did in batch:  # write every requested DID, so resume never re-asks
                p = got.get(did, {})
                f.write(json.dumps({
                    "author_id": did,
                    "author_followers": p.get("followersCount"),
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                }) + "\n")
                n += 1
            if (i // 25) % 40 == 0:
                print(f"  follower {i}/{len(dids)}", flush=True)
            time.sleep(0.2)
    print(f"follower: +{n} profili -> {AUTHORS}", flush=True)


def main() -> None:
    print("autenticato" if login() else "anonimo (rate limit più stretti)", flush=True)
    df = kept_posts()
    collect_followers(df)   # prima i follower: batch, finisce in fretta
    collect_comments(df)
    print("FATTO", flush=True)


if __name__ == "__main__":
    main()
