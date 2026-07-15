"""Task 2.3 — Correlazione segnale social ↔ movimenti di prezzo (lead/lag + direzione)."""
from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from data import query


def render(where: str) -> None:
    st.subheader("I social anticipano o inseguono il mercato?")
    st.caption("Correlazione fra |variazione di prezzo| e volume social, sfasando la "
               "serie social di ±7 giorni. Picco a lag negativo = anticipano; a lag "
               "positivo = inseguono. Solo coppie sopra il filtro semantico.")
    # leadlag/sentiment_direction non hanno le colonne dei contratti: si filtra
    # per appartenenza all'insieme dei contratti selezionati in sidebar.
    in_sel = f"market_id IN (SELECT market_id FROM contracts WHERE {where})"
    ll = query(f"SELECT lag, avg(r_volume) AS r FROM leadlag "
               f"WHERE {in_sel} GROUP BY 1 ORDER BY 1")
    if ll.empty:
        st.info("Nessun contratto eleggibile con i filtri correnti.")
        return
    peak = int(ll.loc[ll["r"].idxmax(), "lag"])
    fig = px.bar(ll, x="lag", y="r",
                 labels={"lag": "sfasamento (giorni)", "r": "correlazione media"},
                 title=f"Volume social ~ |Δprezzo| — picco a lag {peak:+d} giorni → "
                       f"{'i social inseguono' if peak > 0 else 'i social anticipano' if peak < 0 else 'sincroni'}")
    fig.add_vline(x=0, line_dash="dash", line_color="gray")
    st.plotly_chart(fig, width='stretch')

    st.subheader("E la direzione del sentiment?")
    st.caption("La traccia chiede se la direzione del sentiment è allineata alla "
               "direzione del prezzo. Risposta misurata: no — la correlazione firmata "
               "è ~0 a ogni lag e nei giorni di grande movimento il segno del sentiment "
               "concorda col segno del prezzo il 47,5% delle volte (coin flip, p=0.39). "
               "Il segnale social sta nel QUANTO si parla, non nel COME: la polarità è "
               "sul tema, non sull'esito ('Iran colpirà Israele?' che sale è una brutta "
               "notizia a sentiment negativo).")
    sd = query(f"""
        SELECT lag, avg(r_signed) AS "sentiment firmato ~ Δprezzo",
               avg(r_shift) AS "|shift sentiment| ~ |Δprezzo|"
        FROM sentiment_direction WHERE {in_sel} GROUP BY 1 ORDER BY 1
    """)
    melted = sd.melt(id_vars="lag", var_name="misura", value_name="r")
    fig = px.bar(melted, x="lag", y="r", color="misura", barmode="group",
                 labels={"lag": "sfasamento (giorni)"},
                 title="Correlazioni col sentiment: piatte, nessun picco coerente")
    fig.add_vline(x=0, line_dash="dash", line_color="gray")
    st.plotly_chart(fig, width='stretch')

    st.divider()
    st.subheader("Ispeziona un contratto")
    st.caption("Prezzo (probabilità implicita di 'Yes') sovrapposto all'attività "
               "social giornaliera del contratto — il requisito di visualizzazione "
               "congiunta della traccia.")
    c = query(f"SELECT market_id, question FROM contracts WHERE {where} "
              f"ORDER BY volume DESC")
    if c.empty:
        return
    label = st.selectbox("Contratto", c["question"].tolist())
    mid = c.loc[c["question"] == label, "market_id"].iloc[0]
    price = query(f"""
        SELECT timestamp, price FROM prices
        WHERE market_id = '{mid}' AND outcome IN ('Yes', 'Over') ORDER BY timestamp
    """)
    act = query(f"""
        SELECT date_trunc('day', published_at) AS giorno, count(*) AS n,
               avg(sentiment_score) AS sent
        FROM linked WHERE market_id = '{mid}' GROUP BY 1 ORDER BY 1
    """)
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(x=price["timestamp"], y=price["price"],
                             name="prezzo (prob. implicita)"), secondary_y=False)
    fig.add_trace(go.Bar(x=act["giorno"], y=act["n"], name="post/giorno",
                         opacity=0.4, marker_color=act["sent"],
                         marker=dict(colorscale="RdYlGn", cmin=-0.5, cmax=0.5,
                                     color=act["sent"].fillna(0),
                                     colorbar=dict(title="sentiment"))),
                  secondary_y=True)
    fig.update_layout(title=label, hovermode="x unified")
    st.plotly_chart(fig, width='stretch')
    st.caption("Le barre sono i post al giorno, colorate dal sentiment medio "
               "(rosso=negativo, verde=positivo).")
