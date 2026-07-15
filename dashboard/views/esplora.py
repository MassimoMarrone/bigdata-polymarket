"""Esplora i post — il requisito 'inspect individual posts and examine their
metadata and extracted features' della traccia.

Dal contratto ai suoi post: tabella ordinabile con similarità semantica, sentiment
ed engagement; espandendo un post si vedono testo completo, entità NER, query di
ricerca usata in raccolta, follower dell'autore e il sample di reply raccolto.
"""
from __future__ import annotations

import json

import streamlit as st

from data import query


def render(where: str) -> None:
    c = query(f"SELECT market_id, question, category, resolution_outcome "
              f"FROM contracts WHERE {where} ORDER BY volume DESC")
    if c.empty:
        st.info("Nessun contratto con i filtri correnti.")
        return

    label = st.selectbox("Contratto", c["question"].tolist())
    row = c[c["question"] == label].iloc[0]
    st.caption(f"dominio **{row['category']}** · esito **{row['resolution_outcome']}**")

    posts = query(f"""
        SELECT platform, published_at, author_name, author_followers, text, url,
               sim_mpnet, sentiment, sentiment_score, language,
               like_count, reply_count, repost_count, view_count,
               mentioned_entities, comments, search_query
        FROM linked WHERE market_id = '{row['market_id']}'
        ORDER BY like_count + reply_count + repost_count DESC
    """)
    if posts.empty:
        st.info("Nessun post sopra il filtro semantico per questo contratto.")
        return

    a, b, e = st.columns(3)
    a.metric("Post linkati", len(posts))
    b.metric("Similarità mediana", f"{posts['sim_mpnet'].median():.2f}")
    sent = posts["sentiment_score"].dropna()
    e.metric("Sentiment medio", f"{sent.mean():+.2f}" if len(sent) else "n/d")

    plat = st.radio("Piattaforma", ["tutte", "bluesky", "telegram"], horizontal=True)
    text_q = st.text_input("Cerca nel testo dei post", "")
    view = posts
    if plat != "tutte":
        view = view[view["platform"] == plat]
    if text_q:
        view = view[view["text"].str.contains(text_q, case=False, na=False)]

    st.dataframe(
        view[["platform", "published_at", "author_name", "text", "sim_mpnet",
              "sentiment", "like_count", "reply_count", "url"]],
        width='stretch', hide_index=True, height=320,
        column_config={
            "published_at": st.column_config.DatetimeColumn("data", format="YYYY-MM-DD"),
            "text": st.column_config.TextColumn("testo", width="large"),
            "sim_mpnet": st.column_config.NumberColumn("sim", format="%.2f"),
            "url": st.column_config.LinkColumn("link"),
        })

    st.subheader("Dettaglio post")
    st.caption("I 30 post più rilevanti del filtro corrente, con feature estratte.")
    for _, p in view.head(30).iterrows():
        followers = (f" · {int(p['author_followers'])} follower"
                     if p.notna()["author_followers"] else "")
        with st.expander(f"[{p['platform']}] {p['author_name']}{followers} — "
                         f"{str(p['text'])[:90]}"):
            st.write(p["text"])
            meta = {
                "pubblicato": str(p["published_at"]),
                "lingua": p["language"],
                "similarità (MPNet)": round(float(p["sim_mpnet"]), 3),
                "sentiment": f"{p['sentiment']} ({p['sentiment_score']:+.2f})"
                             if p.notna()["sentiment_score"] else p["sentiment"],
                "engagement": f"{int(p['like_count'] or 0)} like · "
                              f"{int(p['reply_count'] or 0)} reply · "
                              f"{int(p['repost_count'] or 0)} repost"
                              + (f" · {int(p['view_count'])} view"
                                 if p.notna()["view_count"] else ""),
                "query di raccolta": p["search_query"],
                "url": p["url"],
            }
            st.json(meta)
            ents = p["mentioned_entities"]
            if isinstance(ents, str) and ents not in ("null", "[]"):
                st.write("**Entità (NER):** " +
                         ", ".join(str(e[0] if isinstance(e, (list, tuple)) else e)
                                   for e in json.loads(ents)))
            if isinstance(p["comments"], str) and p["comments"]:
                st.write("**Sample di reply:**")
                for cm in json.loads(p["comments"])[:10]:
                    st.markdown(f"> {cm['text']}  \n"
                                f"> — *{cm.get('author_id', '?')}, "
                                f"{cm.get('published_at', '')[:10]}, "
                                f"{cm.get('like_count', 0)} like*")
