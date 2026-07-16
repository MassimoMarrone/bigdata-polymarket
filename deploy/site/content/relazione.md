---
tags: []
date created: Wednesday, July 15th 2026, 2:01:19 pm
date modified: Wednesday, July 15th 2026, 10:46:49 pm
---

## Social Media Signals and Prediction Market Outcomes

### A Data-Driven Study on Polymarket — Relazione Tecnica

**Big Data Engineering 2025/2026 — Track 2 · Prof. Vincenzo Moscato**

Autore: Massimo Marrone · Svolto individualmente

**Codice:** [github.com/MassimoMarrone/bigdata-polymarket](https://github.com/MassimoMarrone/bigdata-polymarket) ·
**Dashboard live e documentazione:** [polymarket.massimomarrone.dev](https://polymarket.massimomarrone.dev)

---

### 1. Introduzione e obiettivo

I *prediction market* come Polymarket aggregano l'intelligenza collettiva sul verificarsi di eventi futuri: il prezzo di un contratto, tra 0 e 1, si legge come la probabilità che il mercato assegna a un esito. Questo progetto studia empiricamente la relazione tra il **discorso sui social media** e gli **esiti dei contratti Polymarket**, su tre domini (politica, finanza, sport).

**Domanda di ricerca.** Il discorso social *anticipa* i movimenti del mercato (segnale predittivo), oppure li *commenta* dopo che sono avvenuti (segnale reattivo)?

**Anticipazione del risultato.** Il discorso social sui prediction market è risultato **reattivo, non predittivo**: il picco di attività social segue di ~1 giorno i movimenti di prezzo (§7).

**Scope.** Task 1 (ingestion), Task 2 (dashboard analitica) e Task 3 opzionale (outcome prediction, §8) completi.

---

### 2. Le fonti dati e una scelta obbligata sulle piattaforme

La traccia indica tre piattaforme social: **Reddit, X (Twitter), Telegram**. Il dataset finale ne
usa **tre — Reddit, Telegram e Bluesky** — dove Bluesky sostituisce X. Ogni scelta di accesso è
stata verificata empiricamente, non assunta.

**Reddit — raccolto via scraping (metodo indicato dal corso).** L'accesso a Reddit non è banale e
va documentato con onestà. L'API ufficiale non è più disponibile in self-service: la registrazione
di un'app *script* su `reddit.com/prefs/apps` non si completa (dopo le restrizioni di fine 2025
l'account viene reindirizzato al modulo di approvazione della *Responsible Builder Policy*), e
l'endpoint pubblico `.json` risponde **HTTP 403** a ogni richiesta da script, anche con user-agent
di browser (blocco anti-bot alla prima chiamata, non un rate-limit — verificato sui log). La via
percorribile, indicata dal docente, è lo **scraping tramite proxy residenziale (Scrapfly)**, che
supera il 403. Con questo metodo si è raccolto per keyword della domanda del contratto, nella
finestra creazione→risoluzione: **6.491 post su 340/380 contratti (89% di copertura)**, la più
alta delle tre piattaforme, con un campione di commenti (17.969) e i follower/karma degli autori.
Due numeri diversi, entrambi veri, che conviene tenere distinti: 89% è la copertura *raccolta*
(contratti con almeno un post trovato); dopo il filtro semantico di §4 restano **328/380 contratti
(86%) e 4.592 post** — è questa la copertura che alimenta l'analisi, ed è il numero che la
dashboard mostra.

**X/Twitter — genuinamente inaccessibile, sostituito con Bluesky.** X è l'unica piattaforma
davvero irraggiungibile, e su tre fronti indipendenti: (1) l'API a pagamento parte da **~$42.000/mese**
(full-archive search *Enterprise-only*, verificato 2026); (2) la ricerca web è **dietro login dal
2023** — un probe di scraping sulla pagina di ricerca restituisce **0 tweet** e la pagina di
fallback "JavaScript is not available", perché i risultati caricano via GraphQL autenticato; (3)
gli scraper disponibili espongono solo *tweet-da-URL* e *profilo* (metadati, nessun timeline di
post), quindi non c'è modo di recuperare tweet a tema per il linking. Al suo posto si usa
**Bluesky**: stessa nicchia (discorso testuale short-form in tempo reale), API pubblica
(`api.bsky.app`) con ricerca full-text storica. Un probe su 12 contratti ha dato 10/12 con ≥5 post
pertinenti (media 65 post/contratto) prima di impegnarsi sull'intero dataset.

**Telegram — API aperta.** Storia completa di 9 canali pubblici (news broadcaster), linkata
offline (§3.3).

Il risultato è uno studio a **tre piattaforme** che copre l'enum della traccia (reddit ✓,
telegram ✓) più Bluesky come sostituto motivato dell'unica genuinamente inaccessibile. E il
confronto cross-platform (Task 2.4) ne esce arricchito: le tre hanno specializzazioni di dominio
diverse e complementari (§7.2).

---

### 3. Task 1 — La pipeline di ingestione

#### 3.1 Architettura a due livelli

La pipeline segue un approccio **ELT** (Extract-Load-Transform), non ETL:

- **Livello raw** (`data/raw/*.jsonl`) — dati grezzi, append-only, immutabili, uno schema per
  fonte. È un data lake in miniatura: **schema-on-read**, i dati sono salvati nel formato nativo e
  interpretati solo alla lettura. Assorbe l'eterogeneità tra piattaforme e sopravvive a un
  collector interrotto senza corruzione.
- **Livello processed** (`data/processed/*.parquet`) — dati normalizzati e uniti, rigenerabili da
  zero dal livello raw con un comando. È il livello analitico.

**Figura 1 — architettura end-to-end.** La freccia che conta è quella che *non* c'è: nessun
collector scrive mai nel livello processed, e nessuna analisi legge mai dal raw. Il livello
processed è interamente ricostruibile con `python -m pipeline.storage`; il raw, invece, è l'unica
cosa che non si può rigenerare (le API cambiano, i post spariscono) ed è per questo append-only.

```mermaid
flowchart TB
  %% dichiarati al contrario: in TB mermaid li dispone da destra a sinistra
  TG["<b>Telegram</b><br/>Telethon · 9 canali"]
  BS["<b>Bluesky</b><br/>AT Protocol"]
  RD["<b>Reddit</b><br/>search.json · Scrapfly"]
  PM["<b>Polymarket</b><br/>Gamma + CLOB API"]

  RJ[("<b>LIVELLO RAW</b> — data/raw/*.jsonl<br/>append-only · immutabile · schema-on-read<br/>420 contratti · 95k prezzi · 166k post grezzi")]

  LK["<b>linking.py</b> — keyword + MPNet ≥ 0.35"]
  EN["<b>enrich.py</b> — lingua · sentiment · NER"]
  ST["<b>storage.py</b> — normalizza · denormalizza · unisce"]

  PQ[("<b>LIVELLO PROCESSED</b> — data/processed/*.parquet<br/>rigenerabile con un comando · colonnare<br/>380 contratti · 61k post · commenti e follower inline")]

  DB{{"<b>DuckDB</b> — query in place, nessun server"}}

  CO["<b>correlation*.py</b><br/>lead/lag · sentiment"]
  PR["<b>predict.py</b><br/>Task 3 · CV temporale"]
  DA["<b>dashboard/app.py</b><br/>Streamlit · 6 view"]

  PM --> RJ
  RD --> RJ
  BS --> RJ
  TG --> RJ
  RJ --> LK --> EN --> ST --> PQ
  PQ --> DB
  DB --> CO
  DB --> PR
  DB --> DA
  CO -.->|"leadlag*.parquet"| PQ
  PR -.->|"results.json"| PQ
```

#### 3.2 Raccolta Polymarket

Contratti risolti e serie storiche di prezzo dalla Gamma API e dalla CLOB API. **420 contratti** risolti raccolti (≥130 per dominio); un filtro di qualità a valle (≥10 snapshot di prezzo — un contratto con 2 punti non può sostenere un'analisi lead/lag) ne promuove **380 al livello analitico** (130 finance / 127 politics / 123 sports — il minimo di 100 per dominio resta ampiamente rispettato), con **95.094 snapshot** di prezzo giornalieri.

Una scelta di campionamento si è rivelata critica. Ordinando i mercati per volume di scambi, i primi N appartenevano a pochissimi *eventi*: un evento Polymarket contiene decine di *mercati* quasi identici (37 mercati "chi nominerà Trump alla Fed?" — uno per candidato; 39 mercati sul prezzo del petrolio WTI — uno per soglia). Il primo campione aveva 356 contratti ma **solo 15 argomenti reali**, il che avrebbe reso impossibile il linking (mercati diversi generano le stesse parole chiave) e statisticamente vuota l'analisi di correlazione. Si è imposto un **tetto di 3 mercati per evento**, portando la diversità tematica da 15 a **129 eventi distinti**.

#### 3.3 Raccolta social

- **Reddit** — ricerca per parole chiave della domanda del contratto (`search.json` via proxy
  Scrapfly), ristretta alla finestra creazione→risoluzione. La ricerca restituisce già il testo del
  post (titolo + selftext), quindi una richiesta per contratto rende ~100 post. **6.491 post, 89%
  di copertura**, più un campione di **17.969 commenti** (thread dei top post per engagement) e i
  follower/karma di 2.966 autori (seconda passata su `/user/about.json`).
- **Bluesky** — ricerca per parole chiave estratte dalla domanda del contratto, ristretta alla
  finestra di vita del contratto, con paginazione autenticata (app password) e un fallback che
  accorcia la query quando è troppo restrittiva. **48.204 post, 97% dei contratti** (90% dopo il
  filtro semantico).
- **Telegram** — si è scaricata la **storia completa** di 9 canali pubblici (news broadcaster)
  nella finestra temporale (111.122 messaggi) e li si è linkati offline: ne restano **7.153
  messaggi su 48% dei contratti** (40% dopo il filtro). È la piattaforma più sparsa: i canali
  news coprono ciò di cui *loro* parlano, non i nostri contratti.

Su tutte e tre le piattaforme il *linking* usa lo **stesso metodo** (keyword → filtro semantico):
è ciò che rende interpretabile il confronto cross-platform — ogni differenza osservata è una
proprietà delle piattaforme, non del metodo.

Lo schema della traccia chiede anche un *campione di reply/commenti* per post e i *follower*
dell'autore "where available". La search di Bluesky non restituisce nessuno dei due, quindi una
**seconda passata mirata** (`bluesky_extra.py`) li ha raccolti sui post mantenuti dal filtro
semantico (**4.565 commenti**, **10.527 profili autore**); la stessa logica vale per Reddit
(commenti + karma). Per Telegram l'equivalente non esiste — i canali broadcast espongono le
visualizzazioni ma non thread pubblici di commenti né follower per autore (il canale *è* l'autore):
documentato come limite di piattaforma.

#### 3.4 Limiti dichiarati per piattaforma

| | Reddit | Bluesky | Telegram |
|---|---|---|---|
| Copertura contratti (raccolta) | **89%** (domini bilanciati) | 97% (dominato dallo sport) | 48% (zero sport) |
| Copertura dopo il filtro semantico | 86% | 90% | 40% |
| Rappresentatività | discussione tematica per subreddit | utenti early-adopter | 9 canali news EN, non gli utenti |
| Campionamento | search per keyword (sort relevance) | search per keyword | storia completa dei canali scelti |
| Engagement | upvote + n. commenti | like/reply/repost | solo visualizzazioni |
| Commenti / follower | campione + karma (follower spesso 0) | campione + follower | non disponibili (broadcast) |
| Sentiment | sui soli post EN | sui soli post EN (88%) | idem |

---

### 4. Il contract-to-post linking (il cuore metodologico)

Collegare un post al contratto giusto è il problema centrale del progetto. Un approccio a sole parole chiave produce falsi positivi **sistematici**: tre contratti sul petrolio WTI (soglie 100$, 105$, 30$ — domande diverse) generano la stessa query e quindi gli stessi post. Correlare il prezzo di un contratto con i post di un altro invaliderebbe tutta l'analisi.

**Pipeline a imbuto in tre stadi:**

1. **Recupero (recall)** — parole chiave, alta copertura, bassa precisione.
2. **Filtro semantico (precision)** — embedding della domanda e del post, similarità coseno, soglia.
   Gira in locale, gratis, applicabile a tutti i post.
3. **Validazione** — un giudice LLM esterno (**Gemini**) valuta in zero-shot la pertinenza su un
   campione stratificato di 200 coppie, per **misurare** la qualità del filtro invece di asserirla.

**Figura 2 — l'imbuto, con i numeri reali.** Il filtro semantico scarta il **36% delle coppie**
recuperate dalle parole chiave: è la misura diretta di quanto un linking a sole keyword sarebbe
stato sbagliato. Si noti che il giudice LLM **non è nella pipeline** — non filtra nulla, è un ramo
laterale che serve solo a misurare il filtro. Metterlo in linea avrebbe significato pagare una
chiamata API per 65k coppie e, soprattutto, non avere più niente con cui validare.

```mermaid
flowchart TB
  A["61.848 post raccolti · 380 contratti<br/>(Reddit 6.491 · Bluesky 48.204 · Telegram 7.153 linkabili)"]
  B["<b>Stadio 1 — Recall</b><br/>parole chiave dalla domanda del contratto<br/>alta copertura, bassa precisione"]
  C[("65.159 coppie<br/>post × contratto candidate")]
  D["<b>Stadio 2 — Precision</b><br/>MPNet bi-encoder, coseno domanda~post<br/>soglia 0.35 · locale, gratis, su tutte le coppie"]
  E[("41.770 coppie sopra soglia<br/>30.642 post unici · −36% scartato")]
  F["<b>Analisi</b><br/>lead/lag · sentiment · Task 3"]

  J["<b>Stadio 3 — Validazione</b><br/>giudice Gemini, zero-shot<br/>campione stratificato 200 coppie"]
  K["<b>κ di Cohen</b><br/>0.434 Bluesky+Telegram<br/>0.504 Reddit<br/>= accordo moderato"]

  A --> B --> C --> D --> E --> F
  E -.->|"campiona"| J --> K
  K -.->|"calibra la soglia"| D

  style J fill:#2A2418,stroke:#E0B15C,color:#E8ECF4
  style K fill:#2A2418,stroke:#E0B15C,color:#E8ECF4
```

#### 4.1 Calibrazione e ablazione dei modelli

Confrontati due modelli di embedding contro il giudice (κ di Cohen come accordo):

| Modello | Soglia | Cohen's κ | Precision | Recall |
|---|---|---|---|---|
| **MPNet** (`all-mpnet-base-v2`) | 0.35 | **0.434** | 0.69 | 0.85 |
| MiniLM (`all-MiniLM-L6-v2`) | 0.45 | 0.410 | 0.72 | 0.70 |

**Validazione su tutte e tre le piattaforme.** Il κ sopra è misurato su Bluesky+Telegram. Il
linking è stato validato *separatamente* anche su Reddit, con lo stesso giudice su un campione
stratificato di 200 coppie: **κ = 0.504** (moderate, fascia alta — leggermente superiore).
Il metodo generalizza: non è calibrato su una piattaforma sola.

**Scelta: MPNet @ 0.35** (accordo *moderato* nella scala di Landis-Koch). Recall alto preferito a precisione alta: i falsi positivi residui si diluiscono nell'aggregazione giornaliera, i falsi negativi cancellano segnale che non torna.

#### 4.2 Un esperimento negativo istruttivo

Si è testato se un **cross-encoder** (che legge domanda e post *insieme*) battesse il bi-encoder. Soglia di successo fissata *prima*: κ > 0.55. Cinque modelli testati; nessuno supera MPNet (miglior cross-encoder: κ=0.426). Il risultato è informativo: il difetto non è **architetturale** (bivs cross-encoding) ma di **obiettivo di addestramento** — questi modelli imparano la *rilevanza topica*, e per un post sul Villarreal e un contratto sul Villarreal la risposta è correttamente "sì"; nessuno sa cercare "il post dice qualcosa su *questa specifica affermazione*".

---

### 5. Preprocessing e arricchimento

- **Rilevamento lingua** — non ci si fida del campo dichiarato; la lingua è rilevata su tutti i
  **45.623 post unici** (tre piattaforme). L'**88%** è in inglese. I post non inglesi restano nel
  dataset (contano per il *volume* di discussione) ma non ricevono sentiment (il modello è inglese):
  dargli un punteggio sarebbe un numero privo di senso.
- **Sentiment** — `cardiffnlp/twitter-roberta-base-sentiment-latest` su **40.527 post inglesi**.
  Distribuzione: 68% neutrale, 16% negativo, 15% positivo. Punteggio con segno, così una media
  giornaliera è direttamente interpretabile.
- **NER** — spaCy su **36.497 post**. Le entità più citate (US, Trump, Iran, Fed, NBA…) confermano
  che il linking aggancia post effettivamente sul tema.
- **Deduplicazione** — un post può legarsi a più contratti legittimamente ("vince il City?" e
  "vince l'Inter?" condividono i post), quindi l'unità è la coppia (post, contratto), non il post.

---

### 6. Task 1.5 — Storage: perché Parquet + DuckDB

La traccia chiede di **motivare** la scelta di storage. Si sono considerate le alternative NoSQL del corso:

- **MongoDB** (documentale) — ottimo per l'eterogeneità di schema e lo streaming; valutato e scartato.
- **Parquet + DuckDB** (colonnare) — **scelto**, perché tutte le query del progetto sono
  **analitiche e colonnari**: prezzo nel tempo, volume di post per giorno, sentiment per dominio.
  I database colonnari sono più efficienti per query analitiche (recupero selettivo di colonne), e
  la ridondanza della denormalizzazione — problematica in scrittura — è ottima quando si fa **solo
  analisi**, perché risparmia le join. DuckDB interroga i Parquet in place, senza server.

**Perché non Spark (misurato, non asserito).** La traccia suggerisce Spark "per dataset *large-scale*". Il nostro è di decine di MB. Si è eseguita la **stessa aggregazione** in DuckDB e PySpark su dati replicati fino a 200×:

| Righe | DuckDB | Spark | Spark più lento |
|---|---|---|---|
| 64.062 (reale) | 0,09s | 9,94s | **106×** |
| 640.620 | 0,11s | 2,38s | 22× |
| 3.203.100 | 0,35s | 2,69s | 7,7× |
| 12.812.400 | 1,03s | 4,88s | 4,8× |

Sui dati reali DuckDB è **~100× più veloce**; il pareggio si estrapola verso ~10⁸ righe, ossia quando i dati non stanno più in una macchina. "Big" è una proprietà del dataset, non un default.

---

### 7. Task 2 — Analisi e risultati

#### 7.1 Descrittiva dei contratti (Task 2.1): il mercato sa in anticipo

Separando i contratti per esito effettivo, il prezzo medio di "Yes" diverge presto:

| Giorni alla risoluzione | Contratti poi vincenti | Contratti poi perdenti |
|---|---|---|
| 120 | 0,49 | 0,09 |
| 30 | 0,59 | 0,09 |
| 7 | 0,70 | 0,06 |

Il mercato prezza correttamente i perdenti (~0,08) fin dall'inizio ed è ben calibrato mesi prima della risoluzione. Ne consegue che i social hanno poco spazio per "anticiparlo", il che affina la domanda di ricerca dai *livelli* ai *movimenti* (§7.3).

#### 7.2 Discorso e confronto cross-platform (Task 2.2 / 2.4): specializzazione complementare

Le tre piattaforme sono specializzate in modo **complementare** — copertura per dominio
(contratti con ≥1 post linkato):

| Piattaforma | Politics (su 127) | Finance (su 130) | Sport (su 123) | Profilo |
|---|---|---|---|---|
| **Reddit** | 117 (92%) | 101 (78%) | 110 (89%) | **bilanciata su tutti i domini** |
| Bluesky | 120 (94%) | 101 (78%) | **122 (99%)** | copre quasi tutto lo sport, discorso utenti |
| Telegram | 70 (55%) | 77 (59%) | **5 (4%)** | politica/finanza, sport praticamente assente |

L'asimmetria è la risposta al Task 2.4: quale piattaforma è più informativa dipende dal dominio,
ed è una proprietà **strutturale**, non un artefatto della raccolta (lo stesso metodo di linking
gira su tutte e tre). Il contrasto forte è sullo sport: Bluesky lo copre quasi tutto (99%),
Telegram praticamente per niente (4%) — 24 volte meno, a parità di metodo. Reddit è la più
equilibrata e in questo senso *riempie i buchi*: dove Telegram è assente, dà comunque l'89%. Su Telegram si erano verificati e scartati 12 canali sportivi alternativi — non esiste
un canale pubblico EN con storico sportivo denso; con Reddit lo sport rientra nel dataset.

#### 7.3 Correlazione segnale-mercato (Task 2.3): i social inseguono

Correlando la **variazione** giornaliera di prezzo (non il livello) con il volume social (ora
aggregato sulle tre piattaforme), e sfasando le serie di ±7 giorni, il picco di correlazione è a
**lag +1 giorno, r = 0,14** — più netto rispetto alle due piattaforme sole (era 0,12), segno che
l'aggiunta di Reddit rafforza il segnale invece di diluirlo. La curva è piatta per lag negativi
(social in anticipo), sale fino a +1 e decade: il profilo classico di un segnale **reattivo**,
coerente su tutti e tre i domini.

**E la direzione del sentiment?** La traccia chiede esplicitamente se la *direzione* del sentiment sia allineata alla direzione dei movimenti e se *shift rapidi* del sentiment aggregato accompagnino i movimenti significativi. Tre misure, tutte negative:

1. **Lead/lag firmato** — r(ΔP, sentiment medio) è piatto a ogni sfasamento (±0,02, picco spurio
   +3gg a r=0,023): nessun profilo coerente.
2. **Allineamento nei giorni di grande movimento** (top decile di |ΔP| per contratto) — il segno
   del sentiment concorda con la direzione del prezzo in **164/345 giorni = 47,5%** (test binomiale
   vs 50%: p=0,389, non significativo; stesso esito in tutti e tre i domini).
3. **Shift di sentiment vs grandi movimenti** — r(|Δsentiment|, |ΔP|) anch'esso piatto (max 0,038).

C'è una ragione strutturale, oltre alla debolezza del segnale: la polarità del sentiment riguarda il *tema*, non l'esito "Yes". Per "Will Iran strike Israel?" un rialzo del prezzo è una *cattiva* notizia — sentiment negativo accompagna legittimamente un prezzo che sale. Misurarlo onestamente, invece di forzare un allineamento, è parte del risultato: **è il volume del discorso a reagire ai movimenti, non la sua polarità a predirli.**

**Le piattaforme non sono intercambiabili (osservazione).** Scomponendo il lead/lag *per
piattaforma* (`correlation_platform.py`) emerge un contrasto tra le due piattaforme ricche di
dati: **Reddit** picca a **lag +1** (reattivo, r=0,073), **Bluesky** a **lag −1** (leggermente
anticipatorio, r=0,071). Il *tipo* di piattaforma sembra contare: la discussione *fra utenti*
(Bluesky) ha un piccolo anticipo, i thread di discussione (Reddit) reagiscono. È una lettura
coerente ma va data con cautela — le correlazioni sono deboli e la differenza Bluesky −1 vs +1 è
piccola. Telegram è troppo sparso per un profilo temporale affidabile (picco a +6, quasi certamente
rumore): un limite dovuto alla copertura del 40%, non un segnale.

**Conclusione.** Il discorso social sui prediction market **commenta il mercato il giorno dopo**,
non lo anticipa (il pattern reattivo domina, confermato su tre piattaforme). Onestamente, le
correlazioni sono deboli in valore assoluto (0,10-0,14): il segnale è consistente in segno e
tempistica, ma modesto — non c'è un forte legame lineare volume↔movimenti. Questo è un risultato,
non un fallimento: coerente con §7.1 (un mercato già efficiente lascia poco spazio a un segnale
esterno).

---

### 8. Task 3 (opzionale) — Outcome prediction dalle feature social

La domanda del Task 3: il discorso social — da solo o in combinazione col prezzo — contiene informazione **statisticamente utile** per prevedere l'esito di risoluzione? Dopo §7 l'ipotesi pre-registrata era chiara: il prezzo dominerà; il numero interessante è se il social vi *aggiunga* qualcosa.

**Setup sperimentale** (`pipeline/predict.py`):

- **Anti-leakage per costruzione**: ogni feature (social E prezzo) è calcolata solo su dati
  antecedenti a *risoluzione − 7 giorni*. I post scritti quando l'esito è di fatto noto
  ("Trump ha nominato X", il giorno dopo la nomina) rivelerebbero l'etichetta.
- **Unità**: contratti binari Yes/No con ≥5 post linkati pre-cutoff → **283 contratti** (24% Yes;
  73 in più rispetto alle due piattaforme, grazie alla copertura Reddit).
- **Cross-validation temporale**, come chiede la traccia: contratti ordinati per data di
  risoluzione, walk-forward a finestra espandibile (5 fold): il modello predice sempre contratti
  che si risolvono *dopo* tutto ciò su cui è stato addestrato.
- **Studio di ablazione sui feature set**, confrontati sugli stessi fold: SOCIAL (volume: n post, post/giorno, growth
  rate; engagement: media/max, frazione high-engagement, follower medi; sentiment: media,
  varianza, frazioni pos/neg, trend), PRICE (prezzo "Yes" al cutoff e a 30gg), COMBINED, e
  LINGUISTIC (TF-IDF dei testi dei post per contratto, vettorizzato per fold).
- **Modelli**: regressione logistica (bilanciata) e gradient boosting.
- **Sbilanciamento delle classi** (25% Yes): è una proprietà della popolazione, non del
  campione — un evento a N candidati produce 1 Yes e N−1 No (già mitigato dal tetto di 3
  market/evento). Non si "bilancia" raccogliendo contratti in base all'etichetta (selection
  bias); si gestisce nel modello (`class_weight`) e nelle metriche: macro-F1 pesa le classi
  allo stesso modo, l'AUC-ROC è indipendente dalla soglia, e la baseline di maggioranza
  (0,756) è dichiarata come termine di paragone.

**Figura 3 — la finestra dei dati, per un contratto.** Il taglio a *risoluzione − 7 giorni* è la
difesa contro il leakage più insidioso di questo progetto: nell'ultima settimana di vita di un
contratto il prezzo converge a 0 o a 1 e i post smettono di *prevedere* per iniziare a
*commentare* un esito ormai noto. Un modello addestrato su quella zona avrebbe un'accuratezza
eccellente e un valore predittivo nullo. La zona rossa è dati che possediamo e che buttiamo via.

```mermaid
gantt
    title Contratto di esempio — risoluzione 30/06
    dateFormat YYYY-MM-DD
    axisFormat %d/%m
    section Contratto
    Vita del contratto (prezzo quotato)        :active, 2026-04-01, 2026-06-30
    section Feature USATE
    Post + prezzi ammessi (fino al cutoff)     :done,   2026-04-01, 2026-06-23
    Prezzo Yes al cutoff e a 30gg              :done,   2026-05-24, 2026-06-23
    section Zona cieca SCARTATA
    7gg buttati                                :crit,   2026-06-23, 2026-06-30
    section Etichetta
    Yes/No                                     :milestone, 2026-06-30, 0d
```

**Risultati** (media su 5 fold; baseline di maggioranza: accuracy 0,756):

| Feature set | Modello | Accuracy | AUC-ROC |
|---|---|---|---|
| Social | LogReg | 0,613 | 0,553 |
| Social | GBoost | 0,694 | 0,563 |
| Linguistiche (TF-IDF) | LogReg | 0,600 | 0,642 |
| **Prezzo** | LogReg | **0,911** | **0,966** |
| Combinato | LogReg | 0,923 | 0,942 |

**Lettura.** (1) Le feature social da sole battono il caso (AUC 0,55-0,64 > 0,5) ma **non battono
la baseline di maggioranza in accuracy**: il segnale esiste ed è debole. Le feature linguistiche
sono le migliori del blocco social (AUC 0,642): *di cosa* si parla è più informativo di *quanto*
se ne parla. (2) Il prezzo al cutoff è quasi un classificatore perfetto (AUC 0,966) — la versione
predittiva del §7.1. (3) Il combinato **non supera in AUC** il prezzo da solo (0,942 vs 0,966):
l'informazione social è già incorporata nel prezzo. È la stessa conclusione di §7.3 riformulata come esperimento di classificazione: il mercato ha già scontato il discorso social.

---

### 9. La dashboard

Dashboard Streamlit interattiva a **sei schede**: le quattro analisi del Task 2 (contratti, discorso social, piattaforme, segnale↔mercato), i risultati del Task 3 (metriche di classificazione per feature set) e una scheda di esplorazione libera del singolo contratto (prezzo + post linkati + sentiment sovrapposti). Architettura modulare — una view per file sotto `dashboard/views/`, un `app.py` di solo routing, filtri condivisi in sidebar (dominio, esito, finestra temporale) applicati a ogni scheda. Legge il livello Parquet via DuckDB con connessione e query cache-ate (`st.cache_resource` / `st.cache_data`); tutti i grafici sui post passano dal filtro semantico (nessun match grezzo raggiunge le visualizzazioni). Ogni scheda è coperta da uno smoke test con `streamlit.testing.AppTest` (`tests/test_dashboard.py`). Avvio: `streamlit run dashboard/app.py`.

La dashboard è **pubblicata e navigabile** su
[polymarket.massimomarrone.dev/app](https://polymarket.massimomarrone.dev/app) (deep-link alle
singole schede con `?view=0…5`), accanto a questa relazione e al log delle decisioni; gli
screenshot delle 6 schede sono in `screenshots/` (tab1…tab6, 1600px).

---

### 10. Riflessione conclusiva

Le scoperte più rilevanti sono nate da **fallimenti e misure**, non da un percorso lineare. Il **campionamento degenere** ha mostrato che il numero di righe non è informazione: 356 contratti
che parlavano di 15 argomenti erano un dataset più povero dei 380 che ne coprono 129. Il **caso
WTI** ha rivelato che il linking è il problema scientifico del progetto e non un dettaglio
implementativo — tre soglie di prezzo diverse generano le stesse parole chiave, e correlare il
prezzo di un contratto con i post di un altro avrebbe invalidato ogni numero a valle. Il
**cross-encoder** che non batte il bi-encoder ha insegnato più di un successo: la diagnosi
(obiettivo di addestramento sbagliato, non architettura sbagliata) vale più del κ mancato. E l'**accesso alle piattaforme** si è rivelato un risultato, non un preliminare: Reddit è stato
raggiunto solo per la via indicata dal corso (proxy Scrapfly) dopo che tutte le vie gratuite hanno
restituito 403, mentre X è rimasto fuori — non per scelta, ma per tre prove empiriche
convergenti documentate in §2. Sapere *perché* una fonte non è collezionabile, e dimostrarlo, è
parte del lavoro di data engineering tanto quanto collezionarla.

La misura sistematica — coverage, κ del giudice su tre piattaforme, benchmark DuckDB/Spark,
lead/lag per piattaforma, ablazione dei feature set — è ciò che distingue un dataset scaricato da
un dataset compreso. Il risultato onesto del progetto è negativo e vale più di uno positivo
inventato: il segnale social esiste (r=0,14) ma è debole, insegue il mercato più di quanto lo
anticipi, e non aggiunge nulla al prezzo per prevedere l'esito (AUC 0,553 contro 0,966). Il
mercato, semplicemente, ha già letto i social.

---

#### Appendice — Riproducibilità

```py
pipeline/polymarket.py     # contratti + prezzi
pipeline/bluesky.py        # post Bluesky (app password in .env)
pipeline/bluesky_extra.py  # seconda passata Bluesky: commenti (thread) + follower autori
pipeline/reddit_scrapfly.py # post Reddit via Scrapfly (search.json, proxy residenziale)
pipeline/reddit_integrate.py # score MPNet + sentiment/NER incrementali per Reddit
pipeline/reddit_kappa.py   # validazione linking Reddit (giudice Gemini) -> κ 0.504
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
