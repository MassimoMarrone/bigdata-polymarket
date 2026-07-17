# Social Media Signals and Prediction Market Outcomes

Big Data Engineering 2025/2026 — Track 2 · Studio empirico della relazione tra discorso
social (Reddit + Bluesky + Telegram) ed esiti dei contratti Polymarket, su tre domini
(politica, finanza, sport). Progetto individuale di Massimo Marrone.

**Live:** [polymarket.massimomarrone.dev](https://polymarket.massimomarrone.dev) —
dashboard, relazione tecnica e log delle decisioni.

**I tre risultati in breve:**

1. **Il mercato sa in anticipo** — prezzo medio "Yes" di vincenti vs perdenti: 0,49 vs 0,09
   già a 120 giorni dalla risoluzione.
2. **Le piattaforme sono complementari, non ridondanti** — dopo il filtro semantico Reddit
   copre l'86% dei contratti ed è l'unica bilanciata sui tre domini; Bluesky il 90% ma con
   il 99% dello sport; Telegram il 40%, con lo sport praticamente assente (4%).
3. **I social non anticipano il mercato** — volume social e |Δprezzo| co-variano **lo
   stesso giorno** (picco a offset 0, r=0,14, profilo simmetrico: nessun lead misurabile
   in nessuna direzione); e nel Task 3 il prezzo da solo (AUC 0,966) batte ogni feature
   set social (0,553-0,642): il discorso è già incorporato nel prezzo.

Dataset: **420 contratti** risolti (380 al livello analitico), 95k snapshot di prezzo,
6,5k post Reddit + 48,2k Bluesky + 111k messaggi Telegram, linking semantico validato con
giudice LLM (κ ≈ 0,43 su Bluesky+Telegram e 0,50 su Reddit, con analisi di sensibilità alla soglia).

X (Twitter) è stato sostituito con Bluesky: è risultato genuinamente inaccessibile su tre
fronti indipendenti (API da ~$42.000/mese, ricerca web dietro login dal 2023, nessuno
scraper con ricerca per tema). La prova è nel capitolo 2 della relazione.

## Dataset (Deliverable 2)

I file coi testi raccolti **non sono nel repo** (`posts.parquet` da solo pesa 29 MB).
Si scaricano a parte — 24,7 MB, Parquet, con dizionario dei campi:

```bash
curl -O https://polymarket.massimomarrone.dev/dataset/dataset-polymarket-social.zip
unzip dataset-polymarket-social.zip -d data/processed/ && \
  mv data/processed/dataset/*.parquet data/processed/ && rmdir data/processed/dataset
```

Contiene testi e identificativi di account reali: uso didattico, non redistribuire.

## Setup

```bash
python3 -m pip install -r requirements.txt
python3 -m spacy download en_core_web_sm
```

Credenziali (solo per ri-raccogliere i dati; non servono per dashboard/analisi):
`.env` con `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` (app password, non la password vera),
`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `SCRAPFLY_KEY` (proxy per Reddit),
`GEMINI_API_KEY` (validazione del linking).

## Dashboard (demo)

```bash
streamlit run dashboard/app.py
```

Sei schede: le 4 analisi del Task 2, i risultati del Task 3 e l'esploratore per contratto.
Deep-link: `?view=0…5`. Serve il dataset scaricato (vedi sopra): con quello la dashboard
gira **senza rieseguire la pipeline**. Gli aggregati derivati (`leadlag*.parquet`,
`sentiment_direction.parquet`, `prediction_results.json`) sono invece versionati qui.

## Pipeline (riproducibilità end-to-end)

In ordine; ogni stadio riprende da dove era stato interrotto (il livello raw è append-only):

```bash
python3 pipeline/polymarket.py           # contratti + serie di prezzo (Gamma/CLOB API)
python3 pipeline/reddit_scrapfly.py      # post Reddit (search.json via proxy Scrapfly)
python3 pipeline/bluesky.py              # post Bluesky (search per keyword)
python3 pipeline/bluesky_extra.py        # commenti (thread) + follower autori
python3 pipeline/telegram.py             # storia completa dei canali (Telethon)
python3 pipeline/link_telegram.py        # linking keyword Telegram
python3 pipeline/linking.py              # filtro semantico MPNet + giudice Gemini
python3 pipeline/reddit_integrate.py     # score + arricchimento incrementali per Reddit
python3 pipeline/reddit_kappa.py         # validazione del linking Reddit -> κ 0,504
python3 pipeline/enrich.py               # lingua, sentiment, NER
python3 pipeline/storage.py              # raw JSONL -> Parquet (livello analitico)
python3 pipeline/correlation.py          # lead/lag volume ~ |dP|
python3 pipeline/correlation_platform.py # lead/lag scomposto per piattaforma
python3 pipeline/sentiment_direction.py  # direzione/shift sentiment ~ dP
python3 pipeline/predict.py              # Task 3: classificazione con CV temporale
python3 pipeline/spark_benchmark.py      # DuckDB vs Spark (richiede JDK 17 + pyspark)
```

## Test

```bash
python3 -m pytest tests/ -q     # smoke test di ogni scheda (AppTest) + feature Task 3
```

## Altri script

```bash
python3 scripts/make_pdf.py           # Relazione.md -> PDF A4 (diagrammi inclusi)
python3 scripts/package_dataset.py    # produce lo zip del Deliverable 2
deploy/site/sync-docs.sh              # allinea i documenti al sito, prima del commit
```

## Struttura

```
pipeline/    collector, linking, arricchimento, analisi, prediction
dashboard/   app Streamlit (app.py = routing, views/ = una scheda per file)
scripts/     PDF, packaging del dataset
deploy/      Docker + nginx + generatore del sito statico
data/raw/    JSONL immutabili per piattaforma (append-only, non versionati)
data/processed/  Parquet + risultati (rigenerabili da raw con storage.py)
tests/       AppTest per scheda + unit test feature engineering
```

La motivazione di ogni scelta (storage, piattaforme, linking, soglie, Task 3) è nel
log decisionale `../Decisioni.md`; la relazione tecnica completa è `../Relazione.md`
(PDF: `../Relazione.pdf`).
