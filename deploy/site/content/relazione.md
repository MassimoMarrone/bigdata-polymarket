# Social Media Signals and Prediction Market Outcomes
## A Data-Driven Study on Polymarket — Relazione Tecnica

**Big Data Engineering 2025/2026 — Track 2 · Prof. Vincenzo Moscato**
Autore: Massimo Marrone · Svolto individualmente

> ⚙️ **BOZZA DI LAVORO (2026-07-15).** Struttura completa, risultati misurati inseriti.
> I punti con 🔲 sono da rifinire insieme. La sezione 8 (dashboard) va corredata di screenshot.

---

## 1. Introduzione e obiettivo

I *prediction market* come Polymarket aggregano l'intelligenza collettiva sul verificarsi di
eventi futuri: il prezzo di un contratto, tra 0 e 1, si legge come la probabilità che il mercato
assegna a un esito. Questo progetto studia empiricamente la relazione tra il **discorso sui social
media** e gli **esiti dei contratti Polymarket**, su tre domini (politica, finanza, sport).

**Domanda di ricerca.** Il discorso social *anticipa* i movimenti del mercato (segnale predittivo),
oppure li *commenta* dopo che sono avvenuti (segnale reattivo)?

**Anticipazione del risultato.** Il discorso social sui prediction market è risultato **reattivo,
non predittivo**: il picco di attività social segue di ~1 giorno i movimenti di prezzo (§7).

**Scope.** Task 1 (ingestion), Task 2 (dashboard analitica) e Task 3 opzionale (outcome
prediction, §8) completi.

---

## 2. Le fonti dati e una scelta obbligata sulle piattaforme

La traccia indica tre piattaforme social: **Reddit, X (Twitter), Telegram**. Due si sono rivelate
inaccessibili, per ragioni tecniche documentabili e non aggirabili in modo lecito:

- **X/Twitter** — API a pagamento, fuori dalla portata di un progetto universitario.
- **Reddit** — a fine 2025 Reddit ha **rimosso la creazione self-service delle chiavi della Data API**;
  l'account viene reindirizzato alla Developer Platform (Devvit), che serve a *scrivere* dentro Reddit,
  non a estrarre dataset. L'endpoint pubblico `.json` risponde **403** a ogni richiesta da script.
  L'unica via autorizzata alla ricerca è il programma *Reddit for Researchers*, che richiede
  affiliazione istituzionale con Principal Investigator e approvazione di un comitato etico — non
  percorribile nei tempi. La *Responsible Builder Policy* vieta sia lo scraping non approvato sia
  l'uso dei dump storici fuori dal programma.

**Sostituzione adottata: Bluesky al posto di X.** Bluesky occupa la stessa nicchia — discorso
testuale, short-form, in tempo reale — e offre una API pubblica (`api.bsky.app`) con ricerca
full-text storica. Un probe di fattibilità su 12 contratti ha dato 10/12 con ≥5 post pertinenti,
media 65 post/contratto, confermando la copertura prima di impegnarsi sull'intero dataset.

Il dataset finale usa dunque **Bluesky + Telegram**. Con due piattaforme il confronto
cross-platform (Task 2.4) resta pienamente eseguibile — anzi, la loro specializzazione opposta
(§7.2) lo rende più interessante.

> 🔲 *Da fare insieme: decidere se accennare che la sostituzione è stata sottoposta al docente su Teams.*

---

## 3. Task 1 — La pipeline di ingestione

### 3.1 Architettura a due livelli

La pipeline segue un approccio **ELT** (Extract-Load-Transform), non ETL:

- **Livello raw** (`data/raw/*.jsonl`) — dati grezzi, append-only, immutabili, uno schema per
  fonte. È un data lake in miniatura: **schema-on-read**, i dati sono salvati nel formato nativo e
  interpretati solo alla lettura. Assorbe l'eterogeneità tra piattaforme e sopravvive a un
  collector interrotto senza corruzione.
- **Livello processed** (`data/processed/*.parquet`) — dati normalizzati e uniti, rigenerabili da
  zero dal livello raw con un comando. È il livello analitico.

### 3.2 Raccolta Polymarket

Contratti risolti e serie storiche di prezzo dalla Gamma API e dalla CLOB API. **420 contratti**
risolti (≥130 per dominio), **95.094 snapshot** di prezzo giornalieri.

Una scelta di campionamento si è rivelata critica. Ordinando i mercati per volume di scambi, i
primi N appartenevano a pochissimi *eventi*: un evento Polymarket contiene decine di *mercati*
quasi identici (37 mercati "chi nominerà Trump alla Fed?" — uno per candidato; 39 mercati sul
prezzo del petrolio WTI — uno per soglia). Il primo campione aveva 356 contratti ma **solo 15
argomenti reali**, il che avrebbe reso impossibile il linking (mercati diversi generano le stesse
parole chiave) e statisticamente vuota l'analisi di correlazione. Si è imposto un **tetto di 3
mercati per evento**, portando la diversità tematica da 15 a **129 eventi distinti**.

### 3.3 Raccolta social

- **Bluesky** — ricerca per parole chiave estratte dalla domanda del contratto, ristretta alla
  finestra di vita del contratto, con paginazione autenticata (app password) e un fallback che
  accorcia la query quando è troppo restrittiva. ~48.000 post, copertura dell'82% dei contratti.
- **Telegram** — a differenza di Bluesky, si è scaricata la **storia completa** di 9 canali pubblici
  (news broadcaster) nella finestra temporale (111.122 messaggi) e li si è linkati offline. Questa
  scelta è deliberata: usare lo *stesso* metodo di linking su entrambe le piattaforme è ciò che
  rende interpretabile il confronto cross-platform — ogni differenza osservata è una proprietà
  delle piattaforme, non dei due metodi.

Lo schema della traccia chiede anche un *campione di reply/commenti* per post e i *follower*
dell'autore "where available". La search di Bluesky non restituisce nessuno dei due, quindi una
**seconda passata mirata** (`bluesky_extra.py`) li ha raccolti solo sui post effettivamente
mantenuti dal filtro semantico: **4.565 commenti** (thread dei top post per engagement di ogni
contratto) e **10.527 profili autore** con follower count. Per Telegram l'equivalente non esiste
— i canali broadcast espongono le visualizzazioni ma non thread pubblici di commenti né una
nozione di follower per autore (il canale *è* l'autore): documentato come limite di piattaforma.

### 3.4 Limiti dichiarati per piattaforma

| | Bluesky | Telegram |
|---|---|---|
| Copertura contratti | 82% | 31% (zero sport) |
| Rappresentatività | utenti early-adopter, non il "pubblico X" | 9 canali news EN, non il discorso degli utenti |
| Campionamento | search per keyword → recall dipende dalla query | storia completa, ma solo dei canali scelti |
| Engagement | like/reply/repost per post | solo visualizzazioni |
| Commenti / follower | campione via seconda passata | non disponibili (broadcast) |
| Sentiment | sui soli post EN (88%) | idem |

---

## 4. Il contract-to-post linking (il cuore metodologico)

Collegare un post al contratto giusto è il problema centrale del progetto. Un approccio a sole
parole chiave produce falsi positivi **sistematici**: tre contratti sul petrolio WTI (soglie 100$,
105$, 30$ — domande diverse) generano la stessa query e quindi gli stessi post. Correlare il prezzo
di un contratto con i post di un altro invaliderebbe tutta l'analisi.

**Pipeline a imbuto in tre stadi:**

1. **Recupero (recall)** — parole chiave, alta copertura, bassa precisione.
2. **Filtro semantico (precision)** — embedding della domanda e del post, similarità coseno, soglia.
   Gira in locale, gratis, applicabile a tutti i post.
3. **Validazione** — un giudice LLM esterno (**Gemini**) valuta in zero-shot la pertinenza su un
   campione stratificato di 200 coppie, per **misurare** la qualità del filtro invece di asserirla.

### 4.1 Calibrazione e ablazione dei modelli

Confrontati due modelli di embedding contro il giudice (κ di Cohen come accordo):

| Modello | Soglia | Cohen's κ | Precision | Recall |
|---|---|---|---|---|
| **MPNet** (`all-mpnet-base-v2`) | 0.35 | **0.434** | 0.69 | 0.85 |
| MiniLM (`all-MiniLM-L6-v2`) | 0.45 | 0.410 | 0.72 | 0.70 |

**Scelta: MPNet @ 0.35** (accordo *moderato* nella scala di Landis-Koch). Recall alto preferito a
precisione alta: i falsi positivi residui si diluiscono nell'aggregazione giornaliera, i falsi
negativi cancellano segnale che non torna.

### 4.2 Un esperimento negativo istruttivo

Si è testato se un **cross-encoder** (che legge domanda e post *insieme*) battesse il bi-encoder.
Soglia di successo fissata *prima*: κ > 0.55. Cinque modelli testati; nessuno supera MPNet (miglior
cross-encoder: κ=0.426). Il risultato è informativo: il difetto non è **architetturale** (bi- vs
cross-encoding) ma di **obiettivo di addestramento** — questi modelli imparano la *rilevanza
topica*, e per un post sul Villarreal e un contratto sul Villarreal la risposta è correttamente
"sì"; nessuno sa cercare "il post dice qualcosa su *questa specifica affermazione*".

---

## 5. Preprocessing e arricchimento

- **Rilevamento lingua** — non ci si fida del campo dichiarato (17.343 post Bluesky non lo hanno);
  la lingua è rilevata. L'88% dei post è in inglese. I post non inglesi restano nel dataset (contano
  per il *volume* di discussione) ma non ricevono sentiment (il modello è inglese): dargli un
  punteggio sarebbe un numero privo di senso.
- **Sentiment** — `cardiffnlp/twitter-roberta-base-sentiment-latest` su 35.872 post inglesi.
  Distribuzione: 68% neutrale, 16% negativo, 16% positivo. Punteggio con segno, così una media
  giornaliera è direttamente interpretabile.
- **NER** — spaCy su 32.222 post. Le entità più citate (US, Trump, Iran, Fed, NBA...) confermano
  che il linking aggancia post effettivamente sul tema.
- **Deduplicazione** — un post può legarsi a più contratti legittimamente ("vince il City?" e
  "vince l'Inter?" condividono i post), quindi l'unità è la coppia (post, contratto), non il post.

---

## 6. Task 1.5 — Storage: perché Parquet + DuckDB

La traccia chiede di **motivare** la scelta di storage. Si sono considerate le alternative NoSQL
del corso:

- **MongoDB** (documentale) — ottimo per l'eterogeneità di schema e lo streaming; valutato e scartato.
- **Parquet + DuckDB** (colonnare) — **scelto**, perché tutte le query del progetto sono
  **analitiche e colonnari**: prezzo nel tempo, volume di post per giorno, sentiment per dominio.
  I database colonnari sono più efficienti per query analitiche (recupero selettivo di colonne), e
  la ridondanza della denormalizzazione — problematica in scrittura — è ottima quando si fa **solo
  analisi**, perché risparmia le join. DuckDB interroga i Parquet in place, senza server.

**Perché non Spark (misurato, non asserito).** La traccia suggerisce Spark "per dataset *large-scale*".
Il nostro è di decine di MB. Si è eseguita la **stessa aggregazione** in DuckDB e PySpark su dati
replicati fino a 200×:

| Righe | DuckDB | Spark | Spark più lento |
|---|---|---|---|
| 64.062 (reale) | 0,09s | 9,94s | **106×** |
| 640.620 | 0,11s | 2,38s | 22× |
| 3.203.100 | 0,35s | 2,69s | 7,7× |
| 12.812.400 | 1,03s | 4,88s | 4,8× |

Sui dati reali DuckDB è **~100× più veloce**; il pareggio si estrapola verso ~10⁸ righe, ossia
quando i dati non stanno più in una macchina. "Big" è una proprietà del dataset, non un default.

---

## 7. Task 2 — Analisi e risultati

### 7.1 Descrittiva dei contratti (Task 2.1): il mercato sa in anticipo

Separando i contratti per esito effettivo, il prezzo medio di "Yes" diverge presto:

| Giorni alla risoluzione | Contratti poi vincenti | Contratti poi perdenti |
|---|---|---|
| 120 | 0,49 | 0,09 |
| 30 | 0,59 | 0,09 |
| 7 | 0,70 | 0,06 |

Il mercato prezza correttamente i perdenti (~0,08) fin dall'inizio ed è ben calibrato mesi prima
della risoluzione. Ne consegue che i social hanno poco spazio per "anticiparlo", il che affina la
domanda di ricerca dai *livelli* ai *movimenti* (§7.3).

### 7.2 Discorso e confronto cross-platform (Task 2.2 / 2.4): specializzazione asimmetrica

Le due piattaforme sono specializzate in modo **opposto**:

- **Bluesky** — dominato dallo **sport**, copre l'**82%** dei contratti. Discorso degli utenti.
- **Telegram** — dominato da **politica e finanza**, copre il **31%**, quasi assente sullo sport
  (verificati e scartati 12 canali sportivi alternativi: non esiste un canale pubblico in inglese
  con storico sportivo denso). Flusso di notizie con engagement.

Questa asimmetria è la risposta al Task 2.4: quale piattaforma è più informativa dipende dal
dominio, ed è una proprietà strutturale, non un artefatto della raccolta.

### 7.3 Correlazione segnale-mercato (Task 2.3): i social inseguono

Correlando la **variazione** giornaliera di prezzo (non il livello) con il volume social, e
sfasando le serie di ±7 giorni, il picco di correlazione è a **lag +1 giorno**, coerente su tutti
e tre i domini (finance 0,105, politics 0,117, sport 0,130). La curva è piatta per lag negativi
(social in anticipo), sale fino a +1 e decade: il profilo classico di un segnale **reattivo**.

**E la direzione del sentiment?** La traccia chiede esplicitamente se la *direzione* del sentiment
sia allineata alla direzione dei movimenti e se *shift rapidi* del sentiment aggregato accompagnino
i movimenti significativi. Tre misure, tutte negative:

1. **Lead/lag firmato** — r(ΔP, sentiment medio) è piatto a ogni sfasamento (±0,02, picco spurio
   +3gg a r=0,023): nessun profilo coerente.
2. **Allineamento nei giorni di grande movimento** (top decile di |ΔP| per contratto) — il segno
   del sentiment concorda con la direzione del prezzo in **164/345 giorni = 47,5%** (test binomiale
   vs 50%: p=0,389, non significativo; stesso esito in tutti e tre i domini).
3. **Shift di sentiment vs grandi movimenti** — r(|Δsentiment|, |ΔP|) anch'esso piatto (max 0,038).

C'è una ragione strutturale, oltre alla debolezza del segnale: la polarità del sentiment riguarda
il *tema*, non l'esito "Yes". Per "Will Iran strike Israel?" un rialzo del prezzo è una *cattiva*
notizia — sentiment negativo accompagna legittimamente un prezzo che sale. Misurarlo onestamente,
invece di forzare un allineamento, è parte del risultato: **è il volume del discorso a reagire ai
movimenti, non la sua polarità a predirli.**

**Conclusione.** Il discorso social sui prediction market **commenta il mercato il giorno dopo**,
non lo anticipa. Onestamente, le correlazioni sono deboli in valore assoluto (0,10-0,13): il segnale
è consistente in segno e tempistica, ma modesto — non c'è un forte legame lineare volume↔movimenti.
Questo è un risultato, non un fallimento: coerente con §7.1 (un mercato già efficiente lascia poco
spazio a un segnale esterno).

---

## 8. Task 3 (opzionale) — Outcome prediction dalle feature social

La domanda del Task 3: il discorso social — da solo o in combinazione col prezzo — contiene
informazione **statisticamente utile** per prevedere l'esito di risoluzione? Dopo §7 l'ipotesi
pre-registrata era chiara: il prezzo dominerà; il numero interessante è se il social vi *aggiunga*
qualcosa.

**Setup sperimentale** (`pipeline/predict.py`):

- **Anti-leakage per costruzione**: ogni feature (social E prezzo) è calcolata solo su dati
  antecedenti a *risoluzione − 7 giorni*. I post scritti quando l'esito è di fatto noto
  ("Trump ha nominato X", il giorno dopo la nomina) rivelerebbero l'etichetta.
- **Unità**: contratti binari Yes/No con ≥5 post linkati pre-cutoff → **210 contratti** (25% Yes).
- **Cross-validation temporale**, come chiede la traccia: contratti ordinati per data di
  risoluzione, walk-forward a finestra espandibile (5 fold): il modello predice sempre contratti
  che si risolvono *dopo* tutto ciò su cui è stato addestrato.
- **Feature set confrontati sugli stessi fold**: SOCIAL (volume: n post, post/giorno, growth
  rate; engagement: media/max, frazione high-engagement, follower medi; sentiment: media,
  varianza, frazioni pos/neg, trend), PRICE (prezzo "Yes" al cutoff e a 30gg), COMBINED, e
  LINGUISTIC (TF-IDF dei testi dei post per contratto, vettorizzato per fold).
- **Modelli**: regressione logistica (bilanciata) e gradient boosting.
- **Sbilanciamento delle classi** (25% Yes): è una proprietà della popolazione, non del
  campione — un evento a N candidati produce 1 Yes e N−1 No (già mitigato dal tetto di 3
  market/evento). Non si "bilancia" raccogliendo contratti in base all'etichetta (selection
  bias); si gestisce nel modello (`class_weight`) e nelle metriche: macro-F1 pesa le classi
  allo stesso modo, l'AUC-ROC è indipendente dalla soglia, e la baseline di maggioranza
  (0,748) è dichiarata come termine di paragone.

**Risultati** (media su 5 fold; baseline di maggioranza: accuracy 0,748):

| Feature set | Modello | Accuracy | Macro-F1 | AUC-ROC |
|---|---|---|---|---|
| Social | LogReg | 0,669 | 0,582 | 0,603 |
| Social | GBoost | 0,726 | 0,511 | 0,559 |
| Linguistiche (TF-IDF) | LogReg | 0,674 | 0,567 | 0,705 |
| **Prezzo** | LogReg | **0,909** | **0,893** | **0,980** |
| Combinato | LogReg | 0,909 | 0,868 | 0,953 |

**Lettura.** (1) Le feature social da sole battono il caso (AUC 0,60-0,70 > 0,5) ma **non battono
nemmeno la baseline di maggioranza in accuracy**: il segnale esiste ed è debole. Le feature
linguistiche sono le migliori del blocco social (AUC 0,705): *di cosa* si parla è più informativo
di *quanto* se ne parla. (2) Il prezzo al cutoff è quasi un classificatore perfetto (AUC 0,980) —
la versione predittiva del §7.1. (3) Il combinato **non supera** il prezzo da solo (0,953 vs
0,980): l'informazione social è già incorporata nel prezzo. È la stessa conclusione di §7.3
riformulata come esperimento di classificazione: il mercato ha già scontato il discorso social.

---

## 9. La dashboard

Dashboard Streamlit interattiva a **sei schede**: le quattro analisi del Task 2 (contratti,
discorso social, piattaforme, segnale↔mercato), i risultati del Task 3 (metriche di
classificazione per feature set) e una scheda di esplorazione libera del singolo contratto
(prezzo + post linkati + sentiment sovrapposti). Architettura modulare — una view per
file sotto `dashboard/views/`, un `app.py` di solo routing, filtri condivisi in sidebar (dominio,
esito, finestra temporale) applicati a ogni scheda. Legge il livello Parquet via DuckDB con
connessione e query cache-ate (`st.cache_resource` / `st.cache_data`); tutti i grafici sui post
passano dal filtro semantico (nessun match grezzo raggiunge le visualizzazioni). Ogni scheda è
coperta da uno smoke test con `streamlit.testing.AppTest` (`tests/test_dashboard.py`).
Avvio: `streamlit run dashboard/app.py`.

Gli screenshot delle 6 schede sono in `screenshots/` (tab1…tab6, 1600px) — da impaginare
nella versione finale del documento.

> 🔲 *Da fare insieme: provare la demo live per l'orale (deep-link: `?view=0…5`).*

---

## 10. Riflessione conclusiva

Tre delle scoperte più rilevanti sono nate da **fallimenti e misure**, non da un percorso lineare:
l'inaccessibilità di Reddit ha imposto di capire *cosa* rende una piattaforma sostituibile; il
campionamento degenere ha mostrato che il numero di righe non è informazione; il caso WTI ha
rivelato che il linking è il problema scientifico del progetto, non un dettaglio implementativo.
La misura sistematica — coverage, κ del giudice, benchmark Spark, lead/lag — è ciò che distingue
un dataset scaricato da un dataset compreso.

---

### Appendice — Riproducibilità

```
pipeline/polymarket.py     # contratti + prezzi
pipeline/bluesky.py        # post Bluesky (app password in .env)
pipeline/bluesky_extra.py  # seconda passata: commenti (thread) + follower autori
pipeline/telegram.py       # messaggi Telegram (sessione Telethon)
pipeline/link_telegram.py  # linking keyword Telegram
pipeline/linking.py        # filtro semantico + giudice Gemini
pipeline/enrich.py         # lingua + sentiment + NER
pipeline/storage.py        # → Parquet
pipeline/correlation.py    # analisi lead/lag (volume)
pipeline/sentiment_direction.py # direzione/shift del sentiment vs movimenti
pipeline/predict.py        # Task 3: prediction con CV temporale
pipeline/spark_benchmark.py# DuckDB vs Spark
dashboard/app.py           # dashboard Streamlit
```
Il log completo delle decisioni con motivazioni è in `Decisioni.md` (15 voci).
