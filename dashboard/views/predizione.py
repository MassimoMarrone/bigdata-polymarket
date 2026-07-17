"""Task 3 — Outcome prediction: le feature social aggiungono qualcosa al prezzo?

Legge i risultati salvati da pipeline/predict.py (prediction_results.json): la
dashboard mostra l'esperimento, non lo ri-esegue (il training con CV temporale
dura minuti, non è materiale da rerun di un widget).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

RESULTS = Path(__file__).resolve().parents[2] / "data" / "processed" / "prediction_results.json"

LABELS = {
    "social/logreg": ("Social", "LogReg"),
    "social/gboost": ("Social", "GBoost"),
    "linguistic/tfidf-logreg": ("Linguistiche (TF-IDF)", "LogReg"),
    "price/logreg": ("Prezzo", "LogReg"),
    "price/gboost": ("Prezzo", "GBoost"),
    "combined/logreg": ("Combinato", "LogReg"),
    "combined/gboost": ("Combinato", "GBoost"),
}


def render(where: str) -> None:  # noqa: ARG001 — l'esperimento è globale, non filtrabile
    if not RESULTS.exists():
        st.info("Risultati non trovati: eseguire `python3 pipeline/predict.py`.")
        return
    res = json.loads(RESULTS.read_text())

    st.subheader("Il discorso social prevede l'esito del contratto?")
    st.caption(
        f"Classificazione binaria Yes/No su {res['n_contracts']} contratti "
        f"({res['yes_rate']:.0%} Yes). Anti-leakage: ogni feature — social E prezzo — "
        f"è calcolata solo su dati fino a {res['cutoff_days']} giorni prima della "
        "risoluzione. Cross-validation temporale walk-forward a 5 fold: il modello "
        "predice sempre contratti che si risolvono dopo quelli su cui è addestrato. "
        "I filtri della sidebar non si applicano: l'esperimento è sull'intero dataset."
    )

    rows = [{"Feature set": LABELS[k][0], "Modello": LABELS[k][1],
             "Accuracy": v["accuracy"], "Macro-F1": v["macro_f1"],
             "AUC-ROC": v["auc_roc"]}
            for k, v in res["sets"].items()]
    df = pd.DataFrame(rows)

    best_price = df[df["Feature set"] == "Prezzo"]["AUC-ROC"].max()
    best_combined = df[df["Feature set"] == "Combinato"]["AUC-ROC"].max()
    best_social = df[df["Feature set"].isin(["Social", "Linguistiche (TF-IDF)"])]["AUC-ROC"].max()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Baseline maggioranza", f"{res['majority_baseline_acc']:.0%}",
              help="Accuracy dicendo sempre 'No'")
    c2.metric("Social (miglior AUC)", f"{best_social:.2f}")
    c3.metric("Prezzo (AUC)", f"{best_price:.2f}")
    c4.metric("Combinato (AUC)", f"{best_combined:.2f}",
              delta=f"{best_combined - best_price:+.2f} vs solo prezzo",
              delta_color="inverse")

    order = ["Social", "Linguistiche (TF-IDF)", "Prezzo", "Combinato"]
    fig = px.bar(df, x="Feature set", y="AUC-ROC", color="Modello", barmode="group",
                 category_orders={"Feature set": order},
                 title="AUC-ROC per feature set (0,5 = caso)")
    fig.add_hline(y=0.5, line_dash="dot", annotation_text="caso")
    st.plotly_chart(fig, width='stretch')

    st.plotly_chart(
        px.bar(df, x="Feature set", y="Accuracy", color="Modello", barmode="group",
               category_orders={"Feature set": order},
               title=f"Accuracy (linea = baseline maggioranza "
                     f"{res['majority_baseline_acc']:.0%})")
        .add_hline(y=res["majority_baseline_acc"], line_dash="dot"),
        width='stretch')

    st.dataframe(df.round(3), width='stretch', hide_index=True)

    st.markdown(
        "**Lettura.** Le feature social battono il caso (AUC 0,55-0,64) ma non la "
        "baseline di maggioranza; le linguistiche (TF-IDF) sono le migliori del blocco "
        "social — *di cosa* si parla informa più di *quanto* se ne parla. Il prezzo al "
        "cutoff è quasi un classificatore perfetto e il combinato **non lo supera**: "
        "l'informazione del discorso social è già incorporata nel prezzo. È la stessa "
        "conclusione della scheda 3 (co-movimento senza anticipo) riformulata come "
        "classificazione — e, a differenza del lead/lag, non dipende da convenzioni "
        "temporali: è sopravvissuta intatta alla rettifica del 17/07."
    )
