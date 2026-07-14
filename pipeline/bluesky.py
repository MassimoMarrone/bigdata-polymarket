"""Collect Bluesky posts for each Polymarket contract (broad keyword retrieval).

This is stage 1 of the linking funnel: cast a wide net with keywords, restricted
to the contract's lifetime. Precision comes later, from the semantic filter — so
recall matters here, not relevance.

Host note: `public.api.bsky.app` answers 403; `api.bsky.app` works unauthenticated.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

SEARCH = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"
AUTH_HOST = "https://bsky.social/xrpc"
UA = {"User-Agent": "bigdata-unina-research/0.1"}

MAX_POSTS = 300  # per contract; deep enough for a time series, cheap enough to run
PAGE = 100  # API maximum

# Anonymous callers get the first page only: any cursor request answers 403.
# With an app password (BSKY_HANDLE / BSKY_APP_PASSWORD in .env) we can paginate.
SESSION: dict[str, str] = {}


def _env() -> dict[str, str]:
    """Credentials from .env (kept out of git), falling back to the environment."""
    import os

    env = dict(os.environ)
    dotenv = Path(__file__).resolve().parents[1] / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip("'\""))
    return env


def login() -> bool:
    """Authenticate with an app password, if one is configured. Returns success."""
    env = _env()
    handle = env.get("BSKY_HANDLE")
    password = env.get("BSKY_APP_PASSWORD")
    if not (handle and password):
        return False
    r = requests.post(f"{AUTH_HOST}/com.atproto.server.createSession",
                      json={"identifier": handle, "password": password},
                      headers=UA, timeout=30)
    r.raise_for_status()
    SESSION["jwt"] = r.json()["accessJwt"]
    return True


def _headers() -> dict:
    if "jwt" in SESSION:
        return {**UA, "Authorization": f"Bearer {SESSION['jwt']}"}
    return UA

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
CONTRACTS = RAW / "polymarket" / "contracts.jsonl"
OUT = RAW / "bluesky" / "posts.jsonl"

# Words that carry no topical signal in a market question ("Will X win by June?").
STOPWORDS = {
    "will", "the", "a", "an", "in", "on", "by", "be", "to", "of", "and", "or",
    "is", "are", "this", "that", "at", "for", "before", "after", "win", "wins",
    "hit", "reach", "any", "other", "who", "what", "when", "which", "vs",
}


def keywords(question: str, n: int = 4) -> str:
    """Topical terms from a contract question, in order of appearance.

    Ordering matters: proper nouns tend to lead ("Manchester City win the UEFA
    Champions League?" -> "Manchester City UEFA Champions").
    """
    words = re.findall(r"[A-Za-z][A-Za-z'&.-]+", question)
    kept = [w for w in words if w.lower() not in STOPWORDS and len(w) > 2]
    return " ".join(kept[:n])


def _ts(iso: str) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(params: dict, retries: int = 5) -> dict:
    for attempt in range(retries):
        try:
            r = requests.get(SEARCH, params=params, headers=_headers(), timeout=45)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.status_code in (403, 429) or r.status_code >= 500:
            # Anonymous callers are throttled with 403 after a few hundred calls,
            # and cursor requests are refused outright. Back off; an app password
            # (BSKY_HANDLE / BSKY_APP_PASSWORD) removes both limits.
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 400:
            return {}  # malformed query (e.g. keywords collapsed to nothing)
        r.raise_for_status()
        return r.json()
    return {}


def _row(post: dict, contract: dict, query: str) -> dict:
    rec = post.get("record", {})
    author = post.get("author", {})
    facets = rec.get("facets") or []
    tags = [
        f["features"][0].get("tag")
        for f in facets
        if f.get("features") and f["features"][0].get("$type", "").endswith("#tag")
    ]
    handle = author.get("handle", "")
    rkey = post.get("uri", "").rsplit("/", 1)[-1]
    return {
        "post_id": post.get("uri"),
        "platform": "bluesky",
        "url": f"https://bsky.app/profile/{handle}/post/{rkey}",
        "market_id": contract["market_id"],
        "search_query": query,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "category": contract["category"],
        "author_id": author.get("did"),
        "author_name": author.get("displayName") or handle,
        "author_url": f"https://bsky.app/profile/{handle}",
        "published_at": rec.get("createdAt"),
        "text": rec.get("text", ""),
        "hashtags": [t for t in tags if t],
        "language": (rec.get("langs") or [None])[0],
        "like_count": post.get("likeCount", 0),
        "reply_count": post.get("replyCount", 0),
        "repost_count": post.get("repostCount", 0),
        "quote_count": post.get("quoteCount", 0),
    }


def posts_for(contract: dict) -> list[dict]:
    """Posts for one contract, backing off to shorter queries when a query is dry.

    Bluesky ANDs the query terms, so a long query can be over-constrained: "US
    strikes Iran by February 28, 2026?" yields "strikes Iran February", and nobody
    writes "February" in a post about Iran. Dropping trailing terms recovers those
    contracts; the semantic filter downstream absorbs the extra noise.
    """
    for width in (4, 3, 2):
        rows = _search(contract, keywords(contract["question"], n=width))
        if rows:
            return rows
    return []


def _search(contract: dict, query: str) -> list[dict]:
    if not query:
        return []
    params = {
        "q": query,
        "limit": PAGE,
        "since": _ts(contract["creation_date"]),
        "until": _ts(contract["close_date"]),
        "sort": "latest",  # chronological: we need the whole lifetime, not the top hits
    }
    rows: list[dict] = []
    cursor = None
    while len(rows) < MAX_POSTS:
        if cursor:
            params["cursor"] = cursor
        data = _get(params)
        batch = data.get("posts") or []
        if not batch:
            break
        rows.extend(_row(p, contract, query) for p in batch)
        cursor = data.get("cursor")
        if not cursor or "jwt" not in SESSION:
            break  # anonymous: the first page is all we are allowed
        time.sleep(0.25)
    return rows[:MAX_POSTS]


def already_done() -> set[str]:
    """Contracts already collected, so a killed run can resume instead of restart."""
    if not OUT.exists():
        return set()
    with OUT.open() as f:
        return {json.loads(line)["market_id"] for line in f}


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    authed = login()
    print("autenticato: paginazione completa" if authed
          else "anonimo: max 100 post per contratto (serve app password per paginare)")
    all_contracts = [json.loads(line) for line in CONTRACTS.open()]

    done = already_done()
    contracts = [c for c in all_contracts if c["market_id"] not in done]
    if done:
        print(f"ripresa: {len(done)} contratti gia' raccolti, ne restano {len(contracts)}")

    n_posts = 0
    covered = 0
    with OUT.open("a") as f:
        for i, c in enumerate(contracts, 1):
            rows = posts_for(c)
            for r in rows:
                f.write(json.dumps(r) + "\n")
            n_posts += len(rows)
            covered += len(rows) >= 5
            if i % 30 == 0:
                print(f"  {i}/{len(contracts)} contratti | {n_posts} post | "
                      f"{covered} con >=5 post", flush=True)
            time.sleep(0.25)

    print(f"\n{n_posts} nuovi post -> {OUT}")
    if contracts:
        print(f"coverage grezza (questo run): {covered}/{len(contracts)} "
              f"({100*covered/len(contracts):.0f}%)")


if __name__ == "__main__":
    main()
