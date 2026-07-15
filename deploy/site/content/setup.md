# Social Media Signals and Prediction Market Outcomes

Big Data Engineering 2025/2026 — Track 2 · Studio empirico della relazione tra discorso
social (Bluesky + Telegram) ed esiti dei contratti Polymarket, su tre domini
(politica, finanza, sport). Progetto individuale di Massimo Marrone.

**I tre risultati in breve:**

1. **Il mercato sa in anticipo** — prezzo medio "Yes" di vincenti vs perdenti: 0,49 vs 0,09
   già a 120 giorni dalla risoluzione.
2. **Specializzazione opposta delle piattaforme** — Bluesky copre l'82% dei contratti
   (dominato dallo sport), Telegram il 31% (politica/finanza, zero sport).
3. **I social inseguono il mercato** — picco di correlazione volume↔|Δprezzo| a **lag +1
   giorno** su tutti i domini; e nel Task 3 il prezzo da solo (AUC 0,98) batte ogni
   combinazione di feature social (0,56-0,70): il discorso è già incorporato nel prezzo.

Dataset: **420 contratti** risolti, 95k snapshot di prezzo, ~51,5k post Bluesky,
111k messaggi Telegram, linking semantico validato con giudice LLM (κ=0,434).

## Setup

```bash
python3 -m pip install -r requirements.txt
python3 -m spacy download en_core_web_sm
```

Credenziali (solo per ri-raccogliere i dati; non servono per dashboard/analisi):
`.env` con `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` (app password, non la password vera),
`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `GEMINI_API_KEY` (validazione linking).

## Dashboard (demo)

```bash
streamlit run dashboard/app.py
```

Sei schede: le 4 analisi del Task 2, i risultati del Task 3 e l'esploratore per contratto.
Deep-link: `?view=0…5`. I dati processed sono inclusi in `data/processed/`: la dashboard
gira senza rieseguire la pipeline.

## Pipeline (riproducibilità end-to-end)

In ordine; ogni stadio riprende da dove era stato interrotto (raw layer append-only):

```bash
python3 pipeline/polymarket.py           # contratti + serie di prezzo (Gamma/CLOB API)
python3 pipeline/bluesky.py              # post Bluesky (search per keyword)
python3 pipeline/bluesky_extra.py        # commenti (thread) + follower autori
python3 pipeline/telegram.py             # storia completa dei canali (Telethon)
python3 pipeline/link_telegram.py        # linking keyword Telegram
python3 pipeline/linking.py              # filtro semantico MPNet + giudice Gemini
python3 pipeline/enrich.py               # lingua, sentiment, NER
python3 pipeline/storage.py              # raw JSONL -> Parquet (livello analitico)
python3 pipeline/correlation.py          # lead/lag volume ~ |dP|
python3 pipeline/sentiment_direction.py  # direzione/shift sentiment ~ dP
python3 pipeline/predict.py              # Task 3: classificazione con CV temporale
python3 pipeline/spark_benchmark.py      # DuckDB vs Spark (richiede JDK 17 + pyspark)
```

## Test

```bash
python3 -m pytest tests/ -q     # smoke test di ogni scheda (AppTest) + feature Task 3
```

## Struttura

```
pipeline/    collector, linking, arricchimento, analisi, prediction
dashboard/   app Streamlit (app.py = routing, views/ = una scheda per file)
data/raw/    JSONL immutabili per piattaforma (append-only)
data/processed/  Parquet + risultati (rigenerabili da raw con storage.py)
tests/       AppTest per scheda + unit test feature engineering
docs/        materiale di supporto
```

La motivazione di ogni scelta (storage, piattaforme, linking, soglie, Task 3) è nel
log decisionale `../Decisioni.md`; la relazione tecnica completa è `../Relazione.md`.
