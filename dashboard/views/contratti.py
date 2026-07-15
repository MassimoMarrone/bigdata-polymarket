"""Task 2.1 — Descrittiva dei contratti Polymarket, e il browse richiesto dalla traccia."""
from __future__ import annotations

import plotly.express as px
import streamlit as st

from data import query


def render(where: str) -> None:
    c = query(f"SELECT * FROM contracts WHERE {where}")
    if c.empty:
        st.info("Nessun contratto con i filtri correnti.")
        return

    a, b, e, f = st.columns(4)
    a.metric("Contratti", len(c))
    b.metric("Eventi distinti", c["event_id"].nunique())
    e.metric("Durata mediana", f"{int(c['duration_days'].median())} gg")
    f.metric("Volume mediano", f"${c['volume'].median():,.0f}")

    left, right = st.columns(2)
    left.plotly_chart(px.histogram(c, x="duration_days", color="category", nbins=40,
                                   title="Durata dei contratti (giorni)"),
                      width='stretch')
    right.plotly_chart(px.box(c, x="category", y="volume", color="category", log_y=True,
                              title="Volume di scambi per dominio (log)"),
                       width='stretch')

    left, right = st.columns(2)
    vol = query(f"""
        SELECT c.market_id, c.category,
               stddev(p.price) AS volatilita
        FROM prices p JOIN contracts c USING (market_id)
        WHERE {where} AND p.outcome IN ('Yes', 'Over')
        GROUP BY 1, 2
    """)
    left.plotly_chart(px.box(vol, x="category", y="volatilita", color="category",
                             title="Volatilità del prezzo per dominio (σ)"),
                      width='stretch')
    right.plotly_chart(px.bar(c["category"].value_counts().reset_index(),
                              x="category", y="count", color="category",
                              title="Contratti per dominio"),
                       width='stretch')

    st.subheader("Il prezzo anticipa l'esito?")
    st.caption("Prezzo medio di 'Yes' in funzione dei giorni alla risoluzione, separato "
               "per come il contratto è finito davvero. Le curve divergono presto → il "
               "mercato sa in anticipo.")
    conv = query(f"""
        SELECT date_diff('day', p.timestamp, c.close_date) AS days_left,
               c.resolution_outcome AS esito, avg(p.price) AS prezzo
        FROM prices p JOIN contracts c USING (market_id)
        WHERE {where} AND c.is_binary AND p.outcome = 'Yes'
          AND date_diff('day', p.timestamp, c.close_date) BETWEEN 0 AND 120
        GROUP BY 1, 2 ORDER BY 1
    """)
    fig = px.line(conv, x="days_left", y="prezzo", color="esito",
                  labels={"days_left": "giorni alla risoluzione",
                          "prezzo": "prezzo medio di 'Yes'"})
    fig.update_xaxes(autorange="reversed")
    st.plotly_chart(fig, width='stretch')

    st.subheader("Sfoglia i contratti")
    st.caption("Filtri per dominio, esito e anno di risoluzione nella sidebar; "
               "ordina cliccando le colonne. Il link apre il mercato su Polymarket.")
    tab = c[["question", "category", "resolution_outcome", "resolution_date",
             "duration_days", "volume", "url"]].sort_values("resolution_date",
                                                            ascending=False)
    st.dataframe(tab, width='stretch', hide_index=True,
                 column_config={
                     "question": st.column_config.TextColumn("domanda", width="large"),
                     "category": "dominio",
                     "resolution_outcome": "esito",
                     "resolution_date": st.column_config.DatetimeColumn(
                         "risolto il", format="YYYY-MM-DD"),
                     "duration_days": "durata (gg)",
                     "volume": st.column_config.NumberColumn("volume $", format="%.0f"),
                     "url": st.column_config.LinkColumn("polymarket"),
                 })
