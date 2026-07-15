"""Task 2.4 — Confronto cross-platform: segnali complementari o ridondanti?"""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from data import query


def render(where: str) -> None:
    st.caption("Bluesky è discorso degli utenti; i canali Telegram sono broadcast di "
               "notizie. Le due piattaforme sono specializzate in modo OPPOSTO per "
               "dominio — segnali complementari, non ridondanti: è la risposta al "
               "confronto cross-platform della traccia.")

    cov = query(f"""
        WITH sel AS (SELECT market_id FROM contracts WHERE {where}),
        per_contract AS (
            SELECT l.market_id, l.platform, count(*) AS n
            FROM linked l JOIN sel USING (market_id) GROUP BY 1, 2
        )
        SELECT platform, count(DISTINCT market_id) AS contratti_coperti,
               sum(n) AS post_totali, median(n) AS post_mediani_per_contratto
        FROM per_contract GROUP BY 1
    """)
    n_sel = query(f"SELECT count(*) n FROM contracts WHERE {where}")["n"].iloc[0]
    a, b = st.columns(2)
    for col, (_, row) in zip((a, b), cov.iterrows()):
        col.metric(f"Coverage {row['platform']}",
                   f"{row['contratti_coperti'] / max(n_sel, 1):.0%}",
                   f"{int(row['post_totali'])} post, mediana "
                   f"{row['post_mediani_per_contratto']:.0f}/contratto")
    st.dataframe(cov, width='stretch', hide_index=True)

    left, right = st.columns(2)
    share = query(f"""
        WITH sel AS (SELECT market_id FROM contracts WHERE {where})
        SELECT l.category, l.platform, count(*) AS n
        FROM linked l JOIN sel USING (market_id) GROUP BY 1, 2
    """)
    left.plotly_chart(px.bar(share, x="platform", y="n", color="category",
                             title="Quota di discorso per piattaforma e dominio",
                             barmode="stack"), width='stretch')

    # Coverage per k: la statistica richiesta esplicitamente dalla traccia
    # ("fraction of contracts with at least k associated posts").
    kcov = query(f"""
        WITH sel AS (SELECT market_id FROM contracts WHERE {where}),
        per_contract AS (
            SELECT l.platform, l.market_id, count(*) AS n
            FROM linked l JOIN sel USING (market_id) GROUP BY 1, 2
        ),
        ks AS (SELECT unnest([1, 5, 10, 25, 50, 100]) AS k)
        SELECT k, platform,
               count(*) FILTER (n >= k) / {max(int(n_sel), 1)}.0 AS frazione
        FROM per_contract, ks GROUP BY 1, 2 ORDER BY 1
    """)
    right.plotly_chart(px.line(kcov, x="k", y="frazione", color="platform",
                               markers=True, log_x=True,
                               title="Frazione di contratti con ≥ k post linkati"),
                       width='stretch')

    st.subheader("Dove una piattaforma batte l'altra")
    st.caption("Contratti per cui una piattaforma è nettamente più informativa "
               "(più post linkati). La specializzazione è strutturale: Bluesky "
               "domina lo sport, Telegram politica e finanza.")
    dom = query(f"""
        WITH sel AS (SELECT market_id, question, category FROM contracts WHERE {where}),
        per_contract AS (
            SELECT l.market_id,
                   sum(CASE WHEN l.platform = 'bluesky' THEN 1 ELSE 0 END) AS bluesky,
                   sum(CASE WHEN l.platform = 'telegram' THEN 1 ELSE 0 END) AS telegram
            FROM linked l JOIN sel USING (market_id) GROUP BY 1
        )
        SELECT s.question, s.category, p.bluesky, p.telegram,
               CASE WHEN p.bluesky > 2 * p.telegram THEN 'bluesky'
                    WHEN p.telegram > 2 * p.bluesky THEN 'telegram'
                    ELSE 'pari' END AS vince
        FROM per_contract p JOIN sel s USING (market_id)
        ORDER BY p.bluesky + p.telegram DESC
    """)
    left, right = st.columns([1, 2])
    left.plotly_chart(px.histogram(dom, x="vince", color="category",
                                   title="Chi è più informativo, per contratto"),
                      width='stretch')
    right.dataframe(dom.head(300), width='stretch', hide_index=True,
                    column_config={"question": st.column_config.TextColumn(
                        "domanda", width="large")})
