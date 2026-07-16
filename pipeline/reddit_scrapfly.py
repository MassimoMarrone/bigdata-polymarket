"""Reddit collector via Scrapfly (metodo indicato dal corso: proxy per superare il 403).

Cerca su Reddit per keyword della domanda del contratto, dentro la finestra
creazione→risoluzione. search.json restituisce gia' il TESTO del post (selftext+title),
quindi UNA richiesta per contratto rende ~100 post pronti — niente fetch per-post costosi.

Costo: ~25-32 crediti Scrapfly per richiesta (residenziale). ~760 richieste per 380
contratti ≈ 23k crediti ≈ dentro il piano Discovery ($30). Riprende da dove interrotto.

Uso:
    export SCRAPFLY_KEY="scp-live-..."   # chiave in env, MAI in chiaro nel codice
    python3 pipeline/reddit_scrapfly.py --limit 15   # test gratis su 15 contratti
    python3 pipeline/reddit_scrapfly.py               # raccolta completa
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import quote

import duckdb

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw" / "reddit"
RAW.mkdir(parents=True, exist_ok=True)
OUT = RAW / "posts.jsonl"

STOP = set("will the a an in on at of to is are be win wins hit close closes reach "
           "there no yes by end during after before this that and or for".split())


def keywords(q: str) -> str:
    toks = re.findall(r"[A-Za-z0-9$.]+", q)
    kept = [t for t in toks if t.lower() not in STOP and len(t) > 1
            and not t.isdigit()]
    return " ".join(kept[:6]) or q


def already_done() -> set[str]:
    if not OUT.exists():
        return set()
    return {json.loads(l)["market_id"] for l in OUT.open() if l.strip()}


def fetch_search(client, query: str) -> list[dict]:
    """Una richiesta di ricerca via Scrapfly. search.json = JSON con selftext."""
    from scrapfly import ScrapeConfig
    url = (f"https://www.reddit.com/search.json?q={quote(query)}"
           f"&sort=relevance&t=all&limit=100&raw_json=1")
    cfg = ScrapeConfig(url, asp=True, country="US",
                       proxy_pool="public_residential_pool", render_js=False)
    resp = client.scrape(cfg)
    try:
        data = json.loads(resp.content)["data"]["children"]
    except Exception:
        return []   # blocco o risposta non-JSON: contratto saltato, non crasha
    return [c["data"] for c in data]


def collect_one(client, c: dict) -> list[dict]:
    q = keywords(c["question"])
    posts = fetch_search(client, q)
    kept = []
    for p in posts:
        ts = p.get("created_utc", 0)
        if not (c["cs"] <= ts <= c["rs"]):     # solo la finestra del contratto
            continue
        text = (p.get("title", "") + "\n" + p.get("selftext", "")).strip()
        kept.append({
            "post_id": p.get("id"),
            "platform": "reddit",
            "url": "https://www.reddit.com" + p.get("permalink", ""),
            "market_id": c["market_id"],
            "search_query": q,
            "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "category": c["category"],
            "author_id": p.get("author_fullname"),
            "author_name": p.get("author"),
            "author_url": f"https://www.reddit.com/user/{p.get('author', '')}",
            "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime(ts)) if ts else None,
            "text": text,
            "hashtags": [],
            "like_count": p.get("ups"),
            "reply_count": p.get("num_comments"),
            "repost_count": None,
            "view_count": None,
            "subreddit": p.get("subreddit"),
        })
    return kept


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None,
                    help="numero di contratti (per test); default: tutti")
    args = ap.parse_args()

    key = os.environ.get("SCRAPFLY_KEY")
    if not key:
        raise SystemExit("Manca SCRAPFLY_KEY nell'ambiente.")
    from scrapfly import ScrapflyClient
    client = ScrapflyClient(key=key)

    con = duckdb.connect()
    rows = con.execute(f"""
        SELECT market_id, question, category,
               epoch(creation_date) cs, epoch(resolution_date) rs
        FROM read_parquet('{PROC / "contracts.parquet"}')
        ORDER BY resolution_date DESC
    """).df().to_dict("records")

    done = already_done()
    todo = [r for r in rows if r["market_id"] not in done]
    if args.limit:
        todo = todo[:args.limit]

    print(f"{len(done)} contratti gia' fatti, {len(todo)} da raccogliere")
    tot = 0
    with OUT.open("a", encoding="utf-8") as f:
        for i, c in enumerate(todo, 1):
            try:
                posts = collect_one(client, c)
            except Exception as e:
                print(f"  [{i}/{len(todo)}] {c['market_id']}: ERR {type(e).__name__}: {e}")
                continue
            for p in posts:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
            f.flush()
            tot += len(posts)
            print(f"  [{i}/{len(todo)}] {c['category']:8s} +{len(posts):3d} in-finestra "
                  f"| '{keywords(c['question'])[:40]}'")

    cov = con.execute(f"""
        SELECT count(DISTINCT market_id) FROM read_json_auto('{OUT}')
    """).fetchone()[0] if OUT.exists() else 0
    print(f"\nTotale: {tot} post nuovi. Contratti con >=1 post Reddit: {cov}")


if __name__ == "__main__":
    main()
