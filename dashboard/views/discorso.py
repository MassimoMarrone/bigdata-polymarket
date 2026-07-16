"""Task 2.2 — Volume, tempi, sentiment, entità e engagement del discorso social."""
from __future__ import annotations

import json

import plotly.express as px
import streamlit as st

from data import query

SENT_COLORS = {"positive": "#2ca02c", "neutral": "#7f7f7f", "negative": "#d62728"}


@st.cache_data(show_spinner=False)
def _top_entities(where: str) -> "pd.DataFrame":
    """Parse NER blobs and rank entities — the loop over 40k rows is the slow part,
    so it is cached per filter combination, not re-run at every widget interaction."""
    import pandas as pd
    ents = query(f"""
        SELECT category, mentioned_entities FROM linked
        WHERE {where} AND mentioned_entities IS NOT NULL
              AND mentioned_entities != 'null'
    """)
    rows = []
    for cat, blob in ents.itertuples(index=False):
        # la colonna può contenere "NaN"/numeri: json.loads li accetta ma non sono liste
        try:
            parsed = json.loads(blob) if isinstance(blob, str) else None
        except (ValueError, TypeError):
            parsed = None
        if not isinstance(parsed, list):
            continue
        for e in parsed:
            name = e[0] if isinstance(e, (list, tuple)) else e
            rows.append((cat, str(name)))
    if not rows:
        return pd.DataFrame()
    return (pd.DataFrame(rows, columns=["category", "entita"])
            .value_counts().rename("n").reset_index()
            .groupby("category").head(12))


def render(where: str) -> None:
    vol = query(f"""
        SELECT platform, category, count(*) AS n FROM linked
        WHERE {where} GROUP BY 1, 2
    """)
    st.plotly_chart(px.bar(vol, x="category", y="n", color="platform", barmode="group",
                           title="Volume di post linkati per dominio e piattaforma"),
                    width='stretch')

    left, right = st.columns(2)
    sent = query(f"""
        SELECT category, sentiment, count(*) AS n FROM linked
        WHERE {where} AND sentiment IS NOT NULL GROUP BY 1, 2
    """)
    left.plotly_chart(px.bar(sent, x="category", y="n", color="sentiment",
                             title="Sentiment per dominio (post EN)",
                             color_discrete_map=SENT_COLORS),
                      width='stretch')
    ts = query(f"""
        SELECT date_trunc('week', published_at) AS settimana, platform, count(*) AS n
        FROM linked WHERE {where} GROUP BY 1, 2 ORDER BY 1
    """)
    right.plotly_chart(px.area(ts, x="settimana", y="n", color="platform",
                               title="Volume del discorso nel tempo"),
                       width='stretch')

    st.subheader("Engagement")
    st.caption("Ogni piattaforma misura l'engagement a modo suo: Reddit upvote+commenti, "
               "Bluesky like/reply/repost, Telegram visualizzazioni di canali broadcast. "
               "Scala log: la distribuzione è a coda lunga.")
    c1, c2, c3 = st.columns(3)
    rdt = query(f"""
        SELECT category, coalesce(like_count,0) + coalesce(reply_count,0) AS engagement
        FROM linked WHERE {where} AND platform = 'reddit'
    """)
    c1.plotly_chart(px.box(rdt, x="category", y="engagement", color="category",
                           log_y=True, title="Reddit: upvote+commenti per post (log)"),
                    width='stretch')
    eng = query(f"""
        SELECT category, like_count + reply_count + repost_count AS engagement
        FROM linked WHERE {where} AND platform = 'bluesky'
    """)
    c2.plotly_chart(px.box(eng, x="category", y="engagement", color="category",
                           log_y=True, title="Bluesky: like+reply+repost (log)"),
                    width='stretch')
    views = query(f"""
        SELECT category, view_count FROM linked
        WHERE {where} AND platform = 'telegram' AND view_count > 0
    """)
    c3.plotly_chart(px.box(views, x="category", y="view_count", color="category",
                           log_y=True, title="Telegram: visualizzazioni (log)"),
                    width='stretch')

    st.subheader("Entità più citate (NER)")
    st.caption("Le entità estratte con spaCy dai post linkati: una verifica qualitativa "
               "che il linking aggancia post davvero sul tema del dominio.")
    top = _top_entities(where)
    if len(top):
        st.plotly_chart(px.bar(top, x="n", y="entita", color="category",
                               orientation="h", facet_col="category",
                               facet_col_wrap=3, height=500,
                               title="Top 12 entità per dominio")
                        .update_yaxes(matches=None, showticklabels=True),
                        width='stretch')
    else:
        st.info("Entità non ancora presenti nel parquet (rigenerare storage).")
