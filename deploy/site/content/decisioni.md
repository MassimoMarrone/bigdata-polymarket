---
tags: [1]
date created: Tuesday, June 16th 2026, 3:43:10 am
date modified: Sunday, July 19th 2026, 1:33:29 pm
---

## Decisioni Tecniche — Big Data Polymarket

Log delle decisioni architetturali prese durante il progetto. Ogni entry spiega **cosa** è stato scelto e **perché**.

---

### Template entry

```py
### [YYYY-MM-DD] Titolo decisione
**Scelta:** ...
**Alternativa scartata:** ...
**Motivazione:** ...
```

---

### [2026-06-04] Storage: DuckDB + Parquet

**Scelta:** JSONL per raw data (append-only, immutabile), Parquet per processed data, DuckDB come engine per analytics.

**Alternative scartate:**

- SQLite: buono per structured data ma schema fisso mal si adatta all'eterogeneità dei social media (campi diversi per piattaforma)
- MongoDB: flessibile ma richiede server e aggiunge complessità infrastrutturale non necessaria per un dataset <10GB locale
- CSV: non efficiente per query temporali, nessun supporto tipi nativi

**Motivazione:**

- Parquet è colonnare → query temporali su `published_at` molto efficienti
- DuckDB legge Parquet direttamente senza caricare tutto in RAM → scalabile
- JSONL preserva i raw data per riproducibilità e debugging
- Nessun server da gestire → setup zero

---

### [2026-06-04] Sentiment: cardiffnlp/twitter-roberta-base-sentiment-latest

**Scelta:** Modello pretrained HuggingFace fine-tuned su testo Twitter/social media.

**Alternative scartate:**

- VADER: basato su lessico, non contestuale, pensato per inglese standard
- TextBlob: troppo semplice per testo social media (slang, ironia)
- Modello custom fine-tuned: richiede labeled data e tempo non disponibile

**Motivazione:**

- Pretrained specificamente su social media text (Twitter → simile a Reddit/Telegram)
- 3 classi (positive/neutral/negative) allineate con la traccia
- Inference rapida, gira su CPU
- Documentato e citabile nella relazione

---

### [2026-06-04] Piattaforme: Reddit + Telegram (no X/Twitter)

> ⛔ **SUPERATA il 2026-07-13** — vedi *Piattaforme: Bluesky + Telegram*. Reddit si è rivelato inaccessibile.

**Scelta:** Solo Reddit (via PRAW) e Telegram (via Telethon).

**Motivazione:** X/Twitter API richiede piano a pagamento (Basic: $100/mese) per accesso alla Search API con dati storici. Non disponibile per un progetto universitario. Reddit e Telegram coprono i domini richiesti (politica, finanza, sport) con API/client gratuiti.

**Impatto sulla traccia:** la traccia cita "tre piattaforme" ma accetta qualsiasi coppia che copra i 3 domini tematici. Coverage stats documentate nel report.

---

### [2026-06-04] Linking Strategy: Keyword Extraction + Search

> ⛔ **SUPERATA il 2026-07-13** — vedi *Linking a imbuto*. Il solo keyword matching produce falsi positivi sistematici.

**Scelta:** Estrazione keywords dalla contract question tramite regex + stopword removal → search API Reddit/Telegram con quelle keywords nel periodo [creation_date, resolution_date].

**Alternative scartate:**

- LLM-based linking: più preciso semanticamente ma costoso (API calls) e non riproducibile
- Entity matching: richiederebbe NER sul contratto + matching con entità nei post → più lento

**Motivazione:**

- Approccio documentabile e giustificabile
- Coverage statistics facili da calcolare e reportare
- Sufficiente per dataset di 100 contratti per dominio
- Controllabile: posso ispezionare le keywords estratte

---

### [2026-06-04] Environment: Conda (no venv)

**Scelta:** `conda create -n bigdata python=3.11` — env vive in `~/anaconda3/envs/bigdata/`, fuori dalla cartella del progetto.

**Alternative scartate:**

- venv / uv `.venv/`: crea cartella 300-500MB dentro il progetto → Nextcloud la sincronizzerebbe inutilmente
- Sistema globale: rischio conflitti con altri progetti

**Motivazione:** Nextcloud sincronizza tutta la cartella Documents. Conda risolve il problema senza bisogno di `.nextcloudignore` o altre configurazioni. La portabilità è identica: su un nuovo dispositivo si ricrea l'env con `conda create -n bigdata python=3.11 && pip install -r requirements.txt`.

---

### [2026-06-04] Scope: No Task 3 (Prediction)

**Scelta:** Non implementare il modello predittivo (Task 3 opzionale).

**Motivazione:** Progetto svolto in solitaria con 19 giorni disponibili. Task 1 + Task 2 completati bene valgono più di Task 3 fatto superficialmente. Priorità alla dashboard funzionante per la demo orale.

---

### [2026-07-13] Campionamento contratti: tetto di 3 market per evento

**Scelta:** Selezionare al massimo **3 market per evento** Polymarket (`MAX_PER_EVENT = 3`), scendendo in profondità nella lista degli eventi risolti fino a raggiungere la quota di 120 contratti per dominio.

**Alternativa scartata:** Prendere i primi N market ordinati per volume di scambi (approccio del primo run).

**Motivazione:** Un singolo *evento* Polymarket contiene decine di *market* quasi identici — l'evento "Who will Trump nominate as Fed Chair?" contiene 37 market (uno per candidato), "What will WTI Crude Oil hit in April 2026?" ne contiene 39 (uno per soglia di prezzo). Ordinando per volume, il primo run ha prodotto 356 contratti concentrati in **soli 15 eventi distinti**. Due conseguenze fatali:

1. **Linking impossibile:** market diversi dello stesso evento generano le stesse keyword, quindi pescherebbero gli stessi post. Il contratto "WTI ≥ 100$" e il contratto "WTI ≥ 30$" — domande opposte — verrebbero associati agli stessi identici post.
2. **Correlazione degenere:** l'analisi segnale-mercato avrebbe ~15 casi realmente indipendenti invece di centinaia, rendendo qualsiasi risultato statisticamente fragile.

**Effetto misurato:** eventi distinti da **15 → 129**. Come effetto collaterale, lo sbilanciamento degli outcome è migliorato da 1:6 a 1:3 (i "No" erano gonfiati proprio dagli eventi multi-candidato, dove per costruzione un solo market risolve "Yes").

---

### [2026-07-13] ~~Piattaforme: Bluesky + Telegram (no Reddit, no X)~~ → SUPERATA il 16/07 per la parte Reddit, vedi *Reintroduzione di Reddit via Scrapfly*

**Scelta:** **Bluesky** (via API pubblica AT Protocol) + **Telegram** (canali pubblici via Telethon).

**Alternative scartate:** Reddit, X/Twitter.

**Motivazione:**

- **X/Twitter:** API a pagamento, fuori budget per un progetto universitario.
- **Reddit — accesso rimosso a livello di piattaforma (verificato con fonti, 2026-07-13):** Reddit ha **rimosso la creazione self-service delle chiavi API a fine 2025**; non è un problema del singolo account. L'unica via autorizzata per la ricerca è il programma **Reddit for Researchers (RFR)**, che richiede affiliazione a università accreditata **con Principal Investigator**, proposta dettagliata e **approvazione di un comitato etico (IRB)** — irrealizzabile nei tempi del progetto, e comunque non previsto dalla traccia. Fonti: [RFR Program](https://support.reddithelp.com/hc/en-us/articles/49381918834964-Reddit-for-Researchers-Program), [Developer Platform & Accessing Reddit Data](https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Accessing-Reddit-Data).
- **Reddit (dettaglio tecnico):** l'account non può creare app sulla Data API legacy (Reddit rimbalza su Devvit, la Developer Platform, che serve a *scrivere* dentro Reddit e non consente estrazione di dataset). L'endpoint pubblico `.json` restituisce **403 da script** su ogni forma testata (`/search.json`, `/r/<sub>.json`, `/r/<sub>/hot.json`, permalink, `old.reddit.com`): funziona solo da browser con cookie di sessione. Aggirarlo — via headless browser o cookie hijacking — ricadrebbe nel "circumvent safety mechanisms" vietato dalla **Responsible Builder Policy** di Reddit. La stessa policy vieta l'uso di dump storici fuori dal programma "Reddit for Researchers", chiudendo anche quella via.
- **Bluesky:** search full-text storica, pubblica, senza credenziali né rate limit ostili. Probe di fattibilità su 12 contratti campione: **10/12 con ≥5 post pertinenti**, media 65 post/contratto (sottostima: limite di paginazione a 100). Copre la stessa nicchia di X — discorso testuale short-form in tempo reale — che la traccia voleva.
- **Nota tecnica:** l'host è `api.bsky.app`; `public.api.bsky.app` risponde 403.

**Impatto sui requisiti:** la traccia nomina tre piattaforme (Reddit, X, Telegram). Con due piattaforme il **Task 2.4 (cross-platform comparison) resta pienamente eseguibile**, che è il requisito sostanziale. La scelta va dichiarata nel report come vincolo di accesso, non nascosta.

---

### [2026-07-13] Canali Telegram: broadcast di notizie, verificati

**Scelta:**

- **politics:** `disclosetv`, `insiderpaper`, `bnonews`, `thespectatorindex`
- **finance:** `WatcherGuru`, `financialjuice`, `Cointelegraph`, `unfolded`
- **sports:** `ESPN`, `onefootball`

**Alternative scartate:** Reuters, AFP, CoinDesk, NBA, SkySportsNews, FabrizioRomanoHere (esistono ma **non espongono anteprima pubblica** → raccolta storica incerta); IntelSlava, MarketTwits (aperti ma **in russo** → incompatibili con il modello di sentiment inglese).

**Motivazione e limite dichiarato:** i canali pubblici Telegram sono **broadcast di notizie**, non conversazione: non producono "opinione degli utenti" ma **flusso informativo con engagement** (view, reazioni, inoltri). Questo NON è un difetto ma un asse di analisi: nel Task 2.4 confrontiamo **discorso degli utenti (Bluesky)** contro **flusso di notizie (Telegram)** e ci chiediamo quale dei due anticipa il movimento di prezzo. Limite da dichiarare: **lo sport su Telegram è sotto-rappresentato** (2 canali validi contro 4 degli altri domini).

---

### [2026-07-13] Linking a imbuto: keyword → filtro semantico → LLM-as-Judge per validare

**Scelta:** pipeline di linking a tre stadi.

1. **Recupero largo:** keyword extraction dalla `question` del contratto → search sulla piattaforma, ristretta alla finestra temporale `creation_date → close_date`.
2. **Filtro semantico:** embedding della question e di ogni post, similarità coseno, soglia. Gira in locale, costo zero, applicabile a tutti i post.
3. **Validazione:** un LLM esterno via API (**Gemini 2.5 Flash**) giudica in zero-shot la rilevanza post↔contratto su un **campione stratificato**. Misuriamo l'**accordo** tra il nostro filtro e il giudice (Cohen's κ) → otteniamo una stima *quantitativa* della precisione del linking.

**Alternativa scartata:** solo keyword matching (decisione del 2026-06-04). Produce falsi positivi **sistematici**, non casuali: tre contratti distinti sul WTI (soglie 100$/105$/30$) generano la stessa query `WTI Crude Oil` e quindi lo stesso identico insieme di post. Correlare il prezzo di un contratto con i post di un altro invalida l'intera analisi a valle.

**Alternativa scartata:** LLM su *tutti* i post. Costo e tempo insostenibili su decine di migliaia di post, a 8 giorni dalla consegna.

**Perché questa struttura:** la traccia chiede esplicitamente di *documentare e giustificare la strategia di linking* e di riportare **coverage statistics** (frazione di contratti con ≥k post). L'imbuto ci dà entrambe le cose: la pipeline scala su tutto il dataset a costo zero, e la qualità del filtro è **misurata**, non asserita. È anche la voce su cui si guadagnano punti in *Design choices* e *Creativity*.

**Estensione prevista:** confronto tra **più modelli di embedding** per lo stadio 2, con il giudice LLM come riferimento comune → si ottiene un piccolo studio di ablazione sulla scelta del modello, ulteriore materiale per la sezione *Experiments*.

---

### [2026-07-13] Telegram: linking per contenuto, non per canale — e lo sport è assente

**Scelta:** scaricare la **storia completa** dei canali nella finestra dei contratti (111.122 messaggi) e linkare **offline** con lo stesso imbuto usato per Bluesky, invece di fare una ricerca server-side per contratto dentro ogni canale.

**Motivazione (metodologica, importante per il Task 2.4):** se le due piattaforme fossero linkate con metodi diversi, il confronto cross-platform sarebbe **confuso**: non si potrebbe distinguere una differenza *fra le piattaforme* da una differenza *fra i due metodi di linking*. Un solo metodo su entrambe rende le differenze osservate attribuibili alle piattaforme. Effetto collaterale utile: l'etichetta dominio→canale diventa solo metadata, non un vincolo — un contratto sportivo può agganciare messaggi dai canali di news generaliste.

**Scoperta — asimmetria strutturale fra le piattaforme (risultato, non limite):**

- **Bluesky** è dominato dallo **sport** (20.261 post su 44.425).
- **Telegram** è dominato da **politica e finanza** (~110.000 messaggi su 111.122); lo sport è **quasi assente** (285 messaggi).
- Verificati e scartati 12 canali sportivi alternativi (`footballtweet`, `SkySportsNewsHQ`, `GoalGlobal`, `Transfernewslive`, `FabrizioRomano`, `BleacherReport`, `NBAUpdates`, `SportsCenter`, `LiveScore`, `espnfc`, …): o inesistenti, o fermi al 2024, o con una manciata di messaggi. **Non esiste un canale Telegram pubblico in inglese con storico sportivo denso.**

Questo risponde direttamente al Task 2.4 ("identify contracts for which one platform is substantially more informative than the others, and characterize what distinguishes such cases"): la risposta è **strutturale, non contrattuale** — le piattaforme sono specializzate per dominio.

**Canali rimossi:** `thespectatorindex` (ultimo messaggio: febbraio 2020, fuori dalla finestra).

**Nota sui dati:** `disclosetv` cancella i post vecchi — la sua cronologia salta dal 2026 al giugno 2022, quindi contribuisce solo 128 messaggi. Non è un bug di raccolta.

---

### [2026-07-13] Calibrazione del linking: MPNet @ 0.35 (κ = 0.434)

**Risultato misurato** (`pipeline/linking.py`, output in `data/processed/linking_validation.jsonl`): giudice Gemini (`gemini-flash-lite-latest`, zero-shot, temperature 0) su **200 coppie (contratto, post)** campionate in modo **stratificato** lungo tutto il range di similarità. Campione bilanciato: **104/200 rilevanti (52%)** — il giudice non è degenere.

| Modello | Soglia | Cohen's κ | Precision | Recall |
|---|---|---|---|---|
| MiniLM (`all-MiniLM-L6-v2`) | 0.45 | 0.410 | 0.72 | 0.70 |
| **MPNet (`all-mpnet-base-v2`)** | **0.35** | **0.434** | **0.69** | **0.85** |

**Scelta:** MPNet con soglia 0.35 → accordo *moderato* (Landis–Koch). Recall alto (0.85) preferito a precision alta: i falsi positivi residui si diluiscono nell'aggregazione giornaliera del volume/sentiment, mentre i falsi negativi cancellano segnale che non torna più.

**Nota su un errore evitato:** il primo run produceva κ = 0.615 — un numero *dall'aria migliore*, ma calcolato su **10 coppie**, perché la quota gratuita di `gemini-2.5-flash` si era esaurita e gli errori venivano trattati come "verdetto assente" invece che come fallimenti. Aggiunta una **guardia** che rifiuta di riportare il κ sotto le 50 valutazioni valide. Lezione: una metrica che non fallisce rumorosamente può mentire in silenzio.

**Ablazione = materiale per la voce *Experiments*** della griglia di valutazione.

---

### [2026-07-13] Cross-encoder per il linking: ESPERIMENTO NEGATIVO (soglia non superata)

**Ipotesi:** il bi-encoder confronta due vettori compressi separatamente e perde la relazione fine fra domanda e post (falsi positivi tipo *"Villarreal vince la Liga?"* ← *"Villarreal vs Sevilla: statistiche"*). Un **cross-encoder**, che legge domanda e post **insieme**, dovrebbe risolverlo.

**Soglia di successo pre-registrata (prima di eseguire): κ > 0.55.**

**Risultato misurato** (stesse 200 coppie giudicate, stesse metriche — confronto a parità di condizioni):

| Modello | Tipo | Soglia | Cohen's κ | Precision | Recall |
|---|---|---|---|---|---|
| **MPNet `all-mpnet-base-v2`** | **bi-encoder** | **0.35** | **0.434** | 0.69 | 0.85 |
| ms-marco-MiniLM-L-6-v2 | cross-encoder | -4.52 | 0.426 | 0.70 | 0.80 |
| MiniLM `all-MiniLM-L6-v2` | bi-encoder | 0.45 | 0.410 | 0.72 | 0.70 |
| ms-marco-MiniLM-L-12-v2 | cross-encoder | -4.16 | 0.395 | 0.68 | 0.80 |
| stsb-roberta-base | cross-encoder | 0.26 | 0.306 | 0.65 | 0.72 |
| nli-deberta-v3-base | entailment | 0.00 | 0.089 | 0.54 | 0.97 |
| qnli-electra-base | entailment | 0.97 | 0.082 | 0.85 | 0.11 |

⚠️ *Tutti i κ sono il valore migliore trovato cercando la soglia ottimale sul set di valutazione stesso → sono stime ottimistiche (upper bound). Anche così, i cross-encoder non vincono.* **VERDETTO: NO.** Soglia non superata. **Si resta su MPNet @ 0.35.** Esperimento negativo, documentato.

**Perché è un risultato interessante (per la relazione):** l'ipotesi era che il difetto fosse **architetturale** (bivs cross-encoding). È **falsa**: il cross-encoder sbaglia *sugli stessi identici casi*. Il difetto è nell'**obiettivo di addestramento**: MS MARCO addestra alla *rilevanza topica* ("questo testo parla di questo argomento?") — e per un post sul Villarreal e un contratto sul Villarreal la risposta è correttamente *sì*. Nessuno di questi modelli sa cercare *"questo testo dice qualcosa su questa specifica affermazione"*.

I due modelli di **entailment** falliscono in direzioni opposte, il che conferma la diagnosi: `qnli` rifiuta quasi tutto (recall 0.11 — chiede "il passaggio contiene la risposta?", e un post social non risponde mai a "vincerà il Villarreal?"); `nli-deberta` accetta quasi tutto (recall 0.97, precision 0.54 ≈ base rate). Causa comune: **una domanda non è un'ipotesi dichiarativa**, quindi l'entailment non è definito.

**Prossime mosse possibili (non fatte, per tempo):** (a) riformulare la question in ipotesi dichiarativa prima dell'NLI; (b) distillare il giudizio LLM in un classificatore piccolo; (c) fine-tuning di un cross-encoder sulle etichette del giudice (servirebbero >200 coppie).

---

### [2026-07-14] Perché non Spark: DuckDB è 100× più veloce sul nostro dataset (misurato)

**Contesto:** la traccia elenca Spark tra i tool suggeriti ("for scalable preprocessing of **large-scale** datasets"). Il nostro dataset è piccolo (decine di MB). Invece di asserire "Spark è overkill", l'abbiamo **misurato**: `pipeline/spark_benchmark.py` esegue la STESSA aggregazione (post per contratto-giorno + prezzo giornaliero — l'input dell'analisi lead/lag) in DuckDB e PySpark, su dati replicati ×1/×10/×50/×200.

| Scala | Righe | DuckDB | Spark | Spark più lento |
|---|---|---|---|---|
| **1× (reale)** | 64.062 | **0,09s** | 9,94s | **106×** |
| 10× | 640.620 | 0,11s | 2,38s | 22× |
| 50× | 3.203.100 | 0,35s | 2,69s | 7,7× |
| 200× | 12.812.400 | 1,03s | 4,88s | 4,8× |

**Lettura:** sui dati reali DuckDB è **~100× più veloce**. Il divario si restringe con la scala (l'overhead fisso JVM/scheduling/serializzazione di Spark si ammortizza), ma anche a 12,8M di righe Spark resta 5× più lento. Estrapolando, il pareggio è nell'ordine di **10⁸ righe** — cioè quando i dati non stanno più in una macchina, lo scenario per cui Spark esiste. Verificato che i due motori producano lo **stesso risultato** (assert nel bench).

**Scelta:** DuckDB per l'intero progetto. **Risposta all'orale a "perché non Spark?":** non è un limite ma una scelta dimensionata al dato — "big" è una proprietà del dataset, non un aggettivo. Materiale forte per *Design choices*.

---

### [2026-07-14] ~~RISULTATO CENTRALE: i social INSEGUONO il mercato (lag +1 giorno)~~ → RITIRATO il 17/07, vedi ultima voce

**Analisi** (`pipeline/correlation.py`): correlazione fra **|variazione giornaliera di prezzo|** e **volume di post** linkati (MPNet ≥0.35, solo EN), con la serie social sfasata di -7..+7 giorni. 99 contratti con dati sufficienti (≥20 giorni, ≥20 post).

**Risultato:** picco di correlazione a **lag +1 giorno**, in TUTTI e 3 i domini

(finance r=0,136 | sport r=0,106 | politics r=0,075). La curva è ~0 per lag negativi (social in anticipo), sale fino a lag 0, massimo a +1, poi decade → profilo classico di un segnale **reattivo**.

**Interpretazione (risposta alla domanda di ricerca del progetto):** il discorso social sui prediction market è **reattivo, non predittivo** — la gente commenta il giorno DOPO che la notizia ha già mosso il prezzo. Coerente con il risultato #1 (mercato già calibrato mesi prima → poco spazio per anticiparlo).

**Onestà per la relazione:** le correlazioni sono **deboli in assoluto** (0,07-0,14). Il segnale è consistente in segno e timing su tutti i domini, ma modesto: non c'è forte legame lineare volume↔movimenti. Questo È un risultato, non un fallimento — ed è il tipo di conclusione misurata che vale più di un "sì" forzato.

### [2026-07-15] Task 3: cutoff 7 giorni + CV temporale — il social non aggiunge nulla al prezzo

> ℹ️ **Numeri superati dal rerun a 3 piattaforme (16-17/07):** 283 contratti, baseline 0,756,
> prezzo AUC 0,966, miglior social 0,642, combinato 0,942 — conclusione invariata. Il richiamo
> al "lead/lag +1" più sotto è superato dalla rettifica del 17/07 (ultima voce): la conclusione
> di questo esperimento non dipende da quelle convenzioni ed è sopravvissuta intatta.

**Decisione.** Task 3 (opzionale) implementato come confronto controllato di feature set — SOCIAL / PRICE / COMBINED / LINGUISTIC (TF-IDF) — sugli stessi 210 contratti binari e gli stessi 5 fold walk-forward (TimeSeriesSplit su contratti ordinati per data di risoluzione).

**Le due scelte che rendono l'esperimento credibile:**

1. **Cutoff a risoluzione−7gg su TUTTE le feature** (social e prezzo): i post scritti quando
   l'esito è de facto noto rivelerebbero l'etichetta. Senza cutoff l'accuracy social sale in modo
   fittizio — è leakage, non predizione.
2. **Ipotesi pre-registrata** (da §7.1: il mercato è calibrato mesi prima): il prezzo dominerà;
   il numero interessante è se COMBINED > PRICE.

**Risultato (misurato).** Social AUC 0,56-0,60, TF-IDF 0,705, prezzo 0,980, combinato 0,953: il social batte il caso ma non la baseline di maggioranza (0,748 accuracy), e NON aggiunge nulla al prezzo. Coerente con lead/lag (+1 giorno): il mercato ha già scontato il discorso social. Risultati in `data/processed/prediction_results.json`, codice `pipeline/predict.py`.

---

### [2026-07-16] Reintroduzione di Reddit via Scrapfly (terza decisione di piattaforma)

**Scelta:** raccogliere Reddit tramite `search.json` dietro **proxy residenziale Scrapfly**,

budget ~$30 (piano Discovery), collector `pipeline/reddit_scrapfly.py`.

**Perché la voce del 13/07 è superata.** Quella voce escludeva Reddit su due basi: (a) il 403

dell'endpoint pubblico e (b) il timore che aggirarlo ricadesse nel "circumvent safety

mechanisms" della Responsible Builder Policy. La base (b) è cambiata con un fatto nuovo: il

**docente ha indicato esplicitamente Scrapfly** come via per il progetto ("provate con Scrapfly,

se diventa costoso vedete voi"), fornendo anche gli script di scraping del corso — la via del

proxy è quindi quella *sanzionata dalla sede didattica per questo lavoro*, non un aggiramento

deciso in autonomia. Restava il vincolo (a) tecnico-economico: un probe ha verificato che

`search.json` con sort=relevance raggiunge i post storici del 2024 (57/97 su un contratto di

test) a ~32 crediti/richiesta, rendendo la raccolta completa fattibile nel budget.

**Esito misurato:** 6.491 post su 340/380 contratti (89% raccolta, 86% dopo il filtro), 17.969

commenti, follower/karma di ~3.000 autori; κ del linking su Reddit = 0.504 (soglia fissa, nessuna

ricerca). Reddit è l'unica piattaforma bilanciata sui tre domini (§7.2) e ha reso il dataset

conforme all'enum della traccia (reddit ✓, telegram ✓, Bluesky come sostituto motivato di X).

**Ammissione documentale (dall'audit del 17/07):** questa voce è stata scritta il 17/07, a

posteriori — la decisione era del 16 e il log non l'aveva registrata, lasciando in piedi la

contraddizione con la voce del 13/07. Errore di processo, non di merito: registrato qui perché

il log deve dire anche quando ha mancato il suo scopo.

---

### [2026-07-17] RETTIFICA: il "lag +1" era un artefatto — il risultato vero è co-movimento same-day

**Come è emerso.** Review finale pre-consegna: un test sintetico (dati costruiti con un social

che *reagisce* il giorno dopo il movimento) ha prodotto il picco sul lato etichettato

"anticipano". Da lì, due difetti indipendenti che si sommavano:

1. **Etichetta del segno invertita** in `xcorr`: `shift(lag)` con lag positivo accoppia il
   movimento di oggi col volume di IERI (che *precede*), ma la stampa diceva "inseguono".
2. **Timestamp midnight**: tutti gli snapshot di prezzo sono stampati alle 00:00 UTC — il punto
   del giorno *t* è la frontiera *t−1/t*, quindi `diff(t)` è il movimento avvenuto durante il
   giorno *t−1*. Un altro −1 di attribuzione che nessuno stava contando.

**Risultato corretto** (convenzione `offset = giorno volume − giorno movimento`, fissata da

`tests/test_correlation.py` con serie sintetiche che riproducono anche la convenzione midnight):

picco a **offset 0** in aggregato E in tutti e tre i domini (finance 0,134 / politics 0,129 /

sports 0,159), fianchi simmetrici (0,066 a ±1). **Co-movimento same-day, nessun lead misurabile

in nessuna direzione.** Ritirata anche l'osservazione per-piattaforma "Reddit reattivo / Bluesky

anticipatorio" (17/07 mattina): sotto la convenzione corretta i picchi si sparpagliano

(Reddit 0, Bluesky +2, Telegram −5) — rumore.

**Perché il bug è sopravvissuto:** produceva un risultato *plausibile* e coerente con la teoria

(mercati efficienti → i social inseguono). I risultati che confermano le attese sono quelli che

nessuno verifica. La suite di test copriva dashboard e feature del Task 3, non la matematica

delle analisi — esattamente il buco dove il bug viveva.

**Cosa NON cambia:** la tesi del progetto ("il mercato ha già letto i social") resta in piedi,

portata da §7.1 (calibrazione mesi prima) e dal Task 3 (prezzo AUC 0,966 vs social 0,553;

combinato non batte il prezzo). Cambia il §7.3: da claim direzionale a claim di sincronia.

**Per l'orale:** raccontarlo. Un claim ritirato per auto-verifica con test di regressione è

esattamente il metodo che il corso valuta.
