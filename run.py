"""Entrypoint unico della pipeline: `python3 run.py <gruppo>`.

Il DAG degli stadi era finora solo documentato nel README; qui diventa
eseguibile. Gli stadi NON sono equivalenti — alcuni costano denaro (collector
via API/proxy) o ore (modelli) — quindi l'entrypoint li raggruppa per costo
invece di lanciarli ciecamente in fila:

    python3 run.py analyze     # storage -> analisi -> prediction (minuti, sicuro,
                               #   rigenera il livello processed dal raw)
    python3 run.py test        # suite completa
    python3 run.py deliver     # PDF della relazione + zip del dataset
    python3 run.py dashboard   # streamlit run dashboard/app.py
    python3 run.py enrich      # linking semantico + arricchimento (ORE: carica
                               #   MPNet, RoBERTa, spaCy; chiede conferma)
    python3 run.py collect     # SOLO ISTRUZIONI: i collector costano crediti e
                               #   richiedono chiavi; si lanciano deliberatamente

Ogni stadio resta rilanciabile da solo (il vero pregio di una pipeline batch:
quando si rompe uno stadio rilanci quello, non tutto); questo file e' la mappa.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

GROUPS: dict[str, list[str]] = {
    # raw -> processed -> tutti i risultati analitici. Deterministico e sicuro:
    # non tocca il raw, non chiama API, non spende nulla.
    "analyze": [
        "pipeline/storage.py",
        "pipeline/correlation.py",
        "pipeline/correlation_platform.py",
        "pipeline/sentiment_direction.py",
        "pipeline/predict.py",
        "scripts/sensitivity.py",
    ],
    # pesante (modelli in locale, ore) ma gratuito; il giudice Gemini dentro
    # linking.py parte solo se c'e' la chiave in .env.
    "enrich": [
        "pipeline/link_telegram.py",
        "pipeline/linking.py",
        "pipeline/enrich.py",
    ],
    "deliver": [
        "scripts/make_pdf.py",
        "scripts/package_dataset.py",
    ],
}

COLLECT_HELP = """I collector non si lanciano in batch: costano crediti/richieste e vogliono
chiavi in .env. Ordine, se devi ri-raccogliere davvero:

  python3 pipeline/polymarket.py        # gratuito (API pubbliche, rate-limited)
  python3 pipeline/bluesky.py           # gratuito (app password)
  python3 pipeline/bluesky_extra.py     # gratuito, seconda passata
  python3 pipeline/telegram.py          # gratuito (sessione Telethon)
  python3 pipeline/reddit_scrapfly.py   # A PAGAMENTO: ~32 crediti Scrapfly/contratto

Ognuno riprende da dove era stato interrotto (raw append-only + done-file)."""


def run(script: str) -> None:
    print(f"\n=== {script} " + "=" * max(0, 60 - len(script)), flush=True)
    subprocess.run([sys.executable, str(ROOT / script)], check=True, cwd=ROOT)


def main() -> None:
    group = sys.argv[1] if len(sys.argv) > 1 else None

    if group == "test":
        subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                       check=True, cwd=ROOT)
    elif group == "dashboard":
        subprocess.run([sys.executable, "-m", "streamlit", "run",
                        "dashboard/app.py"], cwd=ROOT)
    elif group == "collect":
        print(COLLECT_HELP)
    elif group == "enrich":
        print("Questo gruppo carica MPNet, RoBERTa e spaCy: ORE di calcolo.")
        if input("Procedere? [y/N] ").strip().lower() != "y":
            raise SystemExit("annullato")
        for s in GROUPS["enrich"]:
            run(s)
    elif group in GROUPS:
        for s in GROUPS[group]:
            run(s)
        print(f"\ngruppo '{group}' completato.")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
