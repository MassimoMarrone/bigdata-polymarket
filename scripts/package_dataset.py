"""Impacchetta il Deliverable 2 (dataset) in uno zip consegnabile.

Il dataset non sta nel repo (i file coi testi scrapati sono in .gitignore:
posts.parquet da solo pesa 29 MB), quindi va prodotto un archivio a parte.
Qui si mette insieme il livello `processed` — che E' il dataset strutturato
richiesto dalla Sezione 2 della traccia — con un dizionario dei campi che
mappa uno a uno lo schema chiesto.

Uso:
    python3 scripts/package_dataset.py           # -> Progetto/dataset-polymarket-social.zip
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parents[1]
PROC = HERE / "data" / "processed"
OUT = HERE.parent / "dataset-polymarket-social.zip"

# Il dataset consegnato = lo schema della Sezione 2. Gli aggregati derivati
# (leadlag, sentiment_direction, prediction_results) NON sono il dataset: sono
# risultati, si rigenerano dal codice e stanno gia' nel repo.
FILES = ["contracts.parquet", "prices.parquet", "posts.parquet"]

README = """# Dataset — Social Media Signals and Prediction Market Outcomes

Big Data Engineering 2025/26 — Track 2 · Massimo Marrone
Deliverable 2 (dataset). Codice: https://github.com/MassimoMarrone/bigdata-polymarket

Formato **Parquet** (colonnare) — la motivazione della scelta di storage e' nel
capitolo 6 della relazione. Si leggono senza database ne' server:

```python
import duckdb
duckdb.sql("SELECT * FROM 'contracts.parquet' LIMIT 5")
# oppure: import pandas as pd; pd.read_parquet('posts.parquet')
```

## Contenuto

| file | righe | cos'e' |
|---|---|---|
| `contracts.parquet` | {n_contracts} | contratti Polymarket risolti (130 finance / 127 politics / 123 sports) |
| `prices.parquet` | {n_prices} | serie storiche di prezzo giornaliere, per contratto e per outcome |
| `posts.parquet` | {n_posts} | post social linkati ai contratti (reddit {n_reddit} · bluesky {n_bluesky} · telegram {n_telegram}) |

`posts.parquet` e' **denormalizzato**: autore, entita' NER e campione di commenti
sono colonne del post, non tabelle separate (scelta motivata nel capitolo 6 —
il carico e' di sola analisi, la ridondanza risparmia le join).

## Schema — mappatura sulla Sezione 2 della traccia

### Polymarket Contracts (9/9 campi richiesti)
`market_id` · `question` · `category` · `outcomes` · `resolution_outcome` ·
`resolution_date` · `creation_date` · `close_date` · `url`

In piu': `volume` (volume di scambi cumulato del contratto), `event_id` /
`event_title` (l'evento Polymarket che raggruppa piu' mercati — usato per il
tetto di 3 mercati/evento, cap. 3.2), `duration_days`, `is_binary`.

### Polymarket Price Time Series (4/5 campi richiesti)
`market_id` · `outcome` · `timestamp` · `price`

**`volume` per snapshot: non disponibile.** L'endpoint `prices-history` della
CLOB API restituisce solo timestamp e prezzo; nessun endpoint pubblico espone il
volume per punto. La traccia lo chiede "where available": qui non lo e'. Il
volume cumulato del contratto e' in `contracts.parquet`.

### Social Media Posts (21/21 campi richiesti)
- *Identificazione e provenienza*: `post_id` · `platform` · `url` · `market_id` ·
  `search_query` · `collected_at` · `category`
- *Autore*: `author_id` · `author_name` · `author_url` · `author_followers`
- *Contenuto*: `published_at` · `text` · `hashtags` · `mentioned_entities` (NER
  spaCy) · `language` (rilevata, non dichiarata dalla piattaforma)
- *Engagement*: `like_count` · `reply_count` · `repost_count` · `view_count`
- *Commenti*: `comments` (campione di risposte per post: testo, autore,
  timestamp, engagement)

In piu': `sentiment_label` / `sentiment_score` (cardiffnlp/twitter-roberta-base-
sentiment-latest, solo sui post inglesi), `subreddit`, `channel`,
`channel_domain`, `quote_count`.

## Note di lettura

- **Le piattaforme sono reddit, bluesky, telegram.** La traccia elencava X
  (Twitter): e' risultato genuinamente inaccessibile (API da ~$42.000/mese,
  ricerca web dietro login dal 2023, nessuno scraper con ricerca per tema) ed e'
  stato sostituito con Bluesky, stessa nicchia e API pubblica. La prova empirica
  e' nel capitolo 2 della relazione.
- **Un post puo' comparire su piu' contratti**: l'unita' e' la coppia (post,
  contratto), non il post. "Vince il City?" e "Vince l'Inter?" condividono
  legittimamente dei post.
- **Il file contiene i candidati, non solo i match.** Il filtro semantico
  (MPNet, coseno >= 0.35, cap. 4) e' applicato a valle nelle analisi; qui i post
  ci sono tutti, cosi' la soglia resta ispezionabile e ricalcolabile.
- I campi non disponibili per una piattaforma sono NULL, non zero (Telegram non
  ha follower per autore ne' thread di commenti: il canale *e'* l'autore).

## Provenienza e uso

Dati pubblici raccolti per un progetto universitario, tramite le API ufficiali
(Polymarket, Bluesky, Telegram) e, per Reddit, via proxy residenziale secondo il
metodo indicato dal docente. Contengono testi e identificativi di account reali:
uso didattico, non redistribuire.
"""


def counts() -> dict[str, int]:
    c = duckdb.connect()
    q = lambda s: c.execute(s).fetchone()[0]
    d = {
        "n_contracts": q(f"SELECT count(*) FROM read_parquet('{PROC/'contracts.parquet'}')"),
        "n_prices": q(f"SELECT count(*) FROM read_parquet('{PROC/'prices.parquet'}')"),
        "n_posts": q(f"SELECT count(*) FROM read_parquet('{PROC/'posts.parquet'}')"),
    }
    for pl in ("reddit", "bluesky", "telegram"):
        d[f"n_{pl}"] = q(f"SELECT count(*) FROM read_parquet('{PROC/'posts.parquet'}') "
                         f"WHERE platform='{pl}'")
    return {k: f"{v:,}".replace(",", ".") for k, v in d.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    missing = [f for f in FILES if not (PROC / f).exists()]
    if missing:
        raise SystemExit(f"mancano dal livello processed: {missing}")

    readme = README.format(**counts())
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in FILES:
            z.write(PROC / f, f"dataset/{f}")
            print(f"  + {f}  ({(PROC/f).stat().st_size // 1024} KB)")
        z.writestr("dataset/README.md", readme)
        print("  + README.md (dizionario dei campi)")

    mb = args.out.stat().st_size / 1e6
    raw = sum((PROC / f).stat().st_size for f in FILES) / 1e6
    print(f"\n{args.out}\n  {mb:.1f} MB compressi (da {raw:.1f} MB)")


if __name__ == "__main__":
    main()
