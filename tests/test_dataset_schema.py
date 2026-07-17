"""Conformita' del dataset allo schema della Sezione 2 della traccia.

I conteggi 9/9, 5/5(-1), 21/21 citati nella relazione erano stati misurati a
mano il 16/07; qui diventano assert, cosi' una rigenerazione del livello
processed che perdesse un campo non passerebbe inosservata. Il campo `volume`
per snapshot di prezzo e' assente per limite della CLOB API (dichiarato in
Relazione 3.2 e nel README del dataset) ed e' quindi escluso dai required.
"""
from __future__ import annotations

from pathlib import Path

import pytest

PROC = Path(__file__).resolve().parents[1] / "data" / "processed"

REQUIRED = {
    "contracts.parquet": [
        "market_id", "question", "category", "outcomes", "resolution_outcome",
        "resolution_date", "creation_date", "close_date", "url",
    ],
    "prices.parquet": [
        # "volume" per snapshot: non esposto dalla CLOB API ("where available")
        "market_id", "outcome", "timestamp", "price",
    ],
    "posts.parquet": [
        # identificazione e provenienza
        "post_id", "platform", "url", "market_id", "search_query",
        "collected_at", "category",
        # autore
        "author_id", "author_name", "author_url", "author_followers",
        # contenuto
        "published_at", "text", "hashtags", "mentioned_entities", "language",
        # engagement
        "like_count", "reply_count", "repost_count", "view_count",
        # commenti
        "comments",
    ],
}


@pytest.mark.parametrize("fname", sorted(REQUIRED))
def test_required_fields_present(fname):
    path = PROC / fname
    if not path.exists():
        pytest.skip(f"{fname} non presente (dataset non scaricato/rigenerato)")
    import pyarrow.parquet as pq
    have = set(pq.read_schema(path).names)
    missing = [c for c in REQUIRED[fname] if c not in have]
    assert not missing, f"{fname}: campi dello schema di traccia mancanti: {missing}"


def test_platforms_are_the_three_declared():
    path = PROC / "posts.parquet"
    if not path.exists():
        pytest.skip("posts.parquet non presente")
    import duckdb
    plats = {r[0] for r in duckdb.sql(
        f"SELECT DISTINCT platform FROM '{path}'").fetchall()}
    assert plats == {"reddit", "bluesky", "telegram"}
