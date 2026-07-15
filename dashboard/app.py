"""Streamlit dashboard: Polymarket contracts vs social discourse.

One view module per required analysis in the brief (Task 2.1-2.4) plus a post
explorer, so a reader maps the dashboard onto the brief without a legend. All
post-level views go through the semantic-filtered `linked` view (data.py); raw
keyword hits never reach the charts.

Routing is a sidebar radio over imported modules (not Streamlit's `pages/`
autodiscovery): the views share the connection, the cache and the sidebar
filters, which autodiscovered pages would each re-create.

Avvio:  streamlit run dashboard/app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
import data as d
from views import contratti, discorso, esplora, piattaforme, segnale

st.set_page_config(page_title="Polymarket × Social", layout="wide")

st.title("Segnali social e mercati predittivi")
st.caption("Polymarket come ground truth · Bluesky e Telegram come discorso pubblico · "
           "linking semantico validato con giudice LLM (κ=0.43)")

VIEWS = {
    "1 · Contratti (Task 2.1)": contratti,
    "2 · Discorso social (Task 2.2)": discorso,
    "3 · Segnale ↔ mercato (Task 2.3)": segnale,
    "4 · Confronto piattaforme (Task 2.4)": piattaforme,
    "🔎 Esplora i post": esplora,
}

with st.sidebar:
    choice = st.radio("Analisi", list(VIEWS), label_visibility="collapsed")
where = d.sidebar_filters()

VIEWS[choice].render(where)
