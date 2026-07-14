"""Shared data access for the dashboard, over the Parquet + JSONL processed layer.

One DuckDB connection, registered once. The linked+enriched post view is the join
the whole dashboard needs — semantic filter (MPNet >= threshold), sentiment and
language — so it lives here rather than being re-derived in every tab.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

PROC = Path(__file__).resolve().parents[1] / "data" / "processed"
THRESHOLD = 0.35  # MPNet cosine, calibrated against the judge (Decisioni.md)


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for name in ("contracts", "prices", "posts", "leadlag"):
        f = PROC / f"{name}.parquet"
        if f.exists():
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{f}')")
    con.execute(f"""
        CREATE VIEW scores AS SELECT * FROM read_json_auto('{PROC/'post_scores.jsonl'}')
    """)
    con.execute(f"""
        CREATE VIEW enriched AS SELECT * FROM read_json_auto('{PROC/'post_enriched.jsonl'}')
    """)
    # The spine of every analysis: posts kept by the semantic filter, carrying the
    # contract's domain and the post's sentiment/language.
    con.execute(f"""
        CREATE VIEW linked AS
        SELECT p.post_id, p.market_id, p.platform, p.published_at,
               p.like_count, p.reply_count, p.repost_count,
               c.category, c.question,
               e.sentiment, e.sentiment_score, e.language
        FROM posts p
        JOIN scores s ON p.post_id = s.post_id AND p.market_id = s.market_id
        JOIN contracts c ON p.market_id = c.market_id
        LEFT JOIN enriched e ON p.post_id = e.post_id
        WHERE s.sim_mpnet >= {THRESHOLD}
    """)
    return con
