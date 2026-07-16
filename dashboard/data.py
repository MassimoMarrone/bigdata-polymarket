"""Shared data access for the dashboard, over the Parquet + JSONL processed layer.

One DuckDB connection, registered once. The linked+enriched post view is the join
the whole dashboard needs — semantic filter (MPNet >= threshold), sentiment and
language — so it lives here rather than being re-derived in every view module.

Caching: `query()` wraps every SQL in `st.cache_data`, so a rerun (every widget
interaction re-executes the script top-to-bottom) hits memory, not DuckDB.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

PROC = Path(__file__).resolve().parents[1] / "data" / "processed"
THRESHOLD = 0.35  # MPNet cosine, calibrated against the judge (Decisioni.md)


@st.cache_resource
def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for name in ("contracts", "prices", "posts", "leadlag", "leadlag_platform",
                 "sentiment_direction"):
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
        SELECT p.post_id, p.market_id, p.platform, p.published_at, p.url,
               p.author_name, p.author_followers, p.text, p.search_query,
               p.like_count, p.reply_count, p.repost_count, p.view_count,
               p.mentioned_entities, p.comments,
               c.category, c.question, c.resolution_outcome, c.resolution_date,
               e.sentiment, e.sentiment_score, e.language,
               s.sim_mpnet
        FROM posts p
        JOIN scores s ON p.post_id = s.post_id AND p.market_id = s.market_id
        JOIN contracts c ON p.market_id = c.market_id
        LEFT JOIN enriched e ON p.post_id = e.post_id
        WHERE s.sim_mpnet >= {THRESHOLD}
    """)
    return con


@st.cache_data(show_spinner=False)
def query(sql: str) -> pd.DataFrame:
    """Cached SQL: each distinct query string is computed once per session."""
    return connect().execute(sql).df()


def where_contracts(domains: list[str], outcome: str,
                    years: tuple[int, int] | None = None) -> str:
    """WHERE clause over `contracts` columns, shared by every view."""
    dom = "','".join(domains) or "none"
    w = f"category IN ('{dom}')"
    if outcome != "tutti":
        w += f" AND resolution_outcome = '{outcome}'"
    if years:
        w += (f" AND year(resolution_date) BETWEEN {years[0]} AND {years[1]}")
    return w


def sidebar_filters() -> str:
    """Common sidebar: domain / outcome / resolution-year. Returns WHERE clause."""
    with st.sidebar:
        st.header("Filtri")
        domains = st.multiselect("Dominio", ["politics", "finance", "sports"],
                                 default=["politics", "finance", "sports"])
        outcome = st.selectbox("Esito", ["tutti", "Yes", "No"])
        lo, hi = query("SELECT min(year(resolution_date)) a, "
                       "max(year(resolution_date)) b FROM contracts").iloc[0]
        years = st.slider("Anno di risoluzione", int(lo), int(hi),
                          (int(lo), int(hi))) if lo != hi else None
    return where_contracts(domains, outcome, years)
