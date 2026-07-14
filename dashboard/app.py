"""Streamlit dashboard: Polymarket contracts vs social discourse.

Four tabs, one per required analysis in the brief (Task 2.1-2.4), so a reader maps
the dashboard onto the brief without a legend. All post-level views go through the
semantic-filtered `linked` view (dashboard/data.py); raw keyword hits never reach
the charts.
"""
from __future__ import annotations

import sys
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent))
import data as d

st.set_page_config(page_title="Polymarket × Social", layout="wide")


@st.cache_resource
def db():
    return d.connect()


con = db()

st.title("Segnali social e mercati predittivi")
st.caption("Polymarket come ground truth · Bluesky e Telegram come discorso pubblico · "
           "linking validato con giudice LLM (κ=0.43)")

with st.sidebar:
    st.header("Filtri")
    domains = st.multiselect("Dominio", ["politics", "finance", "sports"],
                             default=["politics", "finance", "sports"])
    outcome = st.selectbox("Esito", ["tutti", "Yes", "No"])

dom = "','".join(domains) or "none"
where = f"category IN ('{dom}')"
if outcome != "tutti":
    where += f" AND resolution_outcome = '{outcome}'"

t1, t2, t3, t4 = st.tabs([
    "1 · Contratti", "2 · Discorso social",
    "3 · Segnale ↔ mercato", "4 · Confronto piattaforme"])

# ── 1. contracts (Task 2.1) ────────────────────────────────────────────────
with t1:
    c = con.execute(f"SELECT * FROM contracts WHERE {where}").df()
    a, b, e, f = st.columns(4)
    a.metric("Contratti", len(c))
    b.metric("Eventi distinti", c["event_id"].nunique())
    e.metric("Durata mediana", f"{int(c['duration_days'].median())} gg")
    f.metric("Volume mediano", f"${c['volume'].median():,.0f}")

    left, right = st.columns(2)
    left.plotly_chart(px.histogram(c, x="duration_days", color="category", nbins=40,
                                   title="Durata dei contratti (giorni)"),
                      use_container_width=True)
    right.plotly_chart(px.box(c, x="category", y="volume", color="category", log_y=True,
                              title="Volume di scambi per dominio (log)"),
                       use_container_width=True)

    st.subheader("Il prezzo anticipa l'esito?")
    st.caption("Prezzo medio di 'Yes' in funzione dei giorni alla risoluzione, separato "
               "per come il contratto è finito davvero. Le curve divergono presto → il "
               "mercato sa in anticipo.")
    conv = con.execute(f"""
        SELECT date_diff('day', p.timestamp, c.close_date) AS days_left,
               c.resolution_outcome AS esito, avg(p.price) AS prezzo
        FROM prices p JOIN contracts c USING (market_id)
        WHERE {where} AND c.is_binary AND p.outcome = 'Yes'
          AND date_diff('day', p.timestamp, c.close_date) BETWEEN 0 AND 120
        GROUP BY 1, 2 ORDER BY 1
    """).df()
    fig = px.line(conv, x="days_left", y="prezzo", color="esito",
                  labels={"days_left": "giorni alla risoluzione",
                          "prezzo": "prezzo medio di 'Yes'"})
    fig.update_xaxes(autorange="reversed")
    st.plotly_chart(fig, use_container_width=True)

# ── 2. discourse (Task 2.2) ────────────────────────────────────────────────
with t2:
    vol = con.execute(f"""
        SELECT platform, category, count(*) AS n FROM linked
        WHERE category IN ('{dom}') GROUP BY 1, 2
    """).df()
    st.plotly_chart(px.bar(vol, x="category", y="n", color="platform", barmode="group",
                           title="Volume di post linkati per dominio e piattaforma"),
                    use_container_width=True)

    left, right = st.columns(2)
    sent = con.execute(f"""
        SELECT category, sentiment, count(*) AS n FROM linked
        WHERE category IN ('{dom}') AND sentiment IS NOT NULL GROUP BY 1, 2
    """).df()
    left.plotly_chart(px.bar(sent, x="category", y="n", color="sentiment",
                             title="Sentiment per dominio",
                             color_discrete_map={"positive": "#2ca02c",
                                                 "neutral": "#7f7f7f",
                                                 "negative": "#d62728"}),
                      use_container_width=True)

    ts = con.execute(f"""
        SELECT date_trunc('week', published_at) AS settimana, platform, count(*) AS n
        FROM linked WHERE category IN ('{dom}') GROUP BY 1, 2 ORDER BY 1
    """).df()
    right.plotly_chart(px.area(ts, x="settimana", y="n", color="platform",
                               title="Volume del discorso nel tempo"),
                       use_container_width=True)

# ── 3. signal vs market (Task 2.3) ─────────────────────────────────────────
with t3:
    st.subheader("I social anticipano o inseguono il mercato?")
    st.caption("Correlazione fra |variazione di prezzo| e volume social, sfasando la "
               "serie social di ±7 giorni. Picco a lag negativo = anticipano; a lag "
               "positivo = inseguono.")
    ll = con.execute(f"""
        SELECT lag, avg(r_volume) AS r FROM leadlag
        WHERE category IN ('{dom}') GROUP BY 1 ORDER BY 1
    """).df()
    peak = int(ll.loc[ll["r"].idxmax(), "lag"])
    fig = px.bar(ll, x="lag", y="r",
                 labels={"lag": "sfasamento (giorni)", "r": "correlazione media"},
                 title=f"Picco a lag {peak:+d} giorni → "
                       f"{'i social inseguono' if peak > 0 else 'i social anticipano' if peak < 0 else 'sincroni'}")
    fig.add_vline(x=0, line_dash="dash", line_color="gray")
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Ispeziona un contratto")
    c = con.execute(f"SELECT * FROM contracts WHERE {where} ORDER BY volume DESC").df()
    if not c.empty:
        label = st.selectbox("Contratto", c["question"].tolist())
        mid = c.loc[c["question"] == label, "market_id"].iloc[0]
        price = con.execute(f"""
            SELECT timestamp, price FROM prices
            WHERE market_id = '{mid}' AND outcome IN ('Yes', 'Over') ORDER BY timestamp
        """).df()
        act = con.execute(f"""
            SELECT date_trunc('day', published_at) AS giorno, count(*) AS n,
                   avg(sentiment_score) AS sent
            FROM linked WHERE market_id = '{mid}' GROUP BY 1 ORDER BY 1
        """).df()
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=price["timestamp"], y=price["price"],
                                 name="prezzo (prob. implicita)"), secondary_y=False)
        fig.add_trace(go.Bar(x=act["giorno"], y=act["n"], name="post/giorno",
                             opacity=0.4), secondary_y=True)
        fig.update_layout(title=label, hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

# ── 4. cross-platform (Task 2.4) ───────────────────────────────────────────
with t4:
    st.caption("Bluesky è discorso degli utenti; i canali Telegram sono broadcast di "
               "notizie. Le due piattaforme sono specializzate per dominio: è la risposta "
               "al confronto cross-platform.")
    cov = con.execute(f"""
        WITH per_contract AS (
            SELECT market_id, platform, count(*) AS n FROM linked
            WHERE category IN ('{dom}') GROUP BY 1, 2
        )
        SELECT platform, count(DISTINCT market_id) AS contratti_coperti,
               sum(n) AS post_totali, median(n) AS post_mediani_per_contratto
        FROM per_contract GROUP BY 1
    """).df()
    st.dataframe(cov, use_container_width=True)

    share = con.execute(f"""
        SELECT category, platform, count(*) AS n FROM linked
        WHERE category IN ('{dom}') GROUP BY 1, 2
    """).df()
    st.plotly_chart(px.bar(share, x="platform", y="n", color="category",
                           title="Quota di discorso per piattaforma e dominio",
                           barmode="stack"), use_container_width=True)
