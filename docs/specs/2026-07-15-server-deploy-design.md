# Deploy su maxserver — polymarket.massimomarrone.dev

Data: 2026-07-15 · Approvato da Max (approccio A, "procedi come meglio credi")

## Obiettivo

Un solo sottodominio pubblico che presenta l'intero progetto: landing EN per recruiter,
documenti IT per il professore, dashboard live. Pronto prima del 21/7.

## Decisioni prese con Max

- **Timing**: prima del 21/7, completo.
- **Esposizione**: un solo sottodominio (`polymarket.massimomarrone.dev`), più pagine.
- **Lingua**: landing e setup EN; Relazione e Decisioni restano IT.
- **Codice**: GitHub pubblico (repo creato da Max); trasferimento sul server via SSH.
- **Dati**: `data/processed/` entra nel repo (~33MB, è il deliverable "dataset");
  `data/raw/` (130MB) e `data/processed/_bench/` (112MB) restano fuori.
  `.env` e `tg.session` MAI nel repo (già in .gitignore, verificato).

## Architettura

```
Cloudflare Tunnel "mioserver" (esistente)
  polymarket.massimomarrone.dev ──► nginx (container "polymarket-site", server_net)
                                      ├─ /            statico: landing EN
                                      ├─ /report      Relazione.md → HTML (IT)
                                      ├─ /decisions   Decisioni.md → HTML (IT)
                                      ├─ /setup       README.md → HTML (EN)
                                      └─ /app  ──proxy──► streamlit (container
                                                "polymarket-dashboard", baseUrlPath=/app)
```

File nel repo, cartella `deploy/`:

- `docker-compose.yml` — 2 servizi su `server_net` (external), nessuna porta host
  (raggiunti dal tunnel via nome container).
- `nginx.conf` — statico + proxy `/app` con header WebSocket
  (`Upgrade`/`Connection`), `proxy_read_timeout` lungo per la sessione Streamlit.
- `Dockerfile.dashboard` — python slim, requirements della sola dashboard
  (streamlit, duckdb, pandas, plotly, pyarrow), copia `dashboard/` + `data/processed/`.
- `site/build.py` — genera `site/dist/` : landing + 3 pagine dai markdown
  (python-markdown, extensions: tables, fenced_code, toc). Gira in fase di build
  dell'immagine nginx (multi-stage) così il server non ha dipendenze python.
- `site/` — template HTML/CSS condiviso + landing.

Relazione.md e Decisioni.md vivono FUORI dal repo (in `Progetto/`): lo script
`deploy/site/sync-docs.sh` li copia in `deploy/site/content/` e va eseguito IN LOCALE
prima del commit quando i documenti cambiano (sul server la copia è già nel repo —
il clone è autosufficiente). build.py legge solo da `content/`.

## Design della landing (EN)

- Tesi in hero: "Markets move first. Social media follows — one day later." con
  mini-chart SVG inline del lead/lag (dati reali).
- Palette scura da terminale di mercato: fondo blu-inchiostro #0B1220, testo #E8ECF4,
  blu-mercato #5B9DFF, ambra-social #E0B15C, pannelli #182236. (Niente nero+verde acido.)
- Type: Spectral (display), IBM Plex Sans (body), IBM Plex Mono (numeri/label) — Google Fonts.
- Sezioni: hero → 3 findings (numeri reali) → pipeline (sequenza vera) → screenshot
  dashboard → engineering choices (DuckDB 100×, κ=0.434, anti-leakage) → footer GitHub/contatti.
- Firma visiva: il chart lead/lag nel hero; il resto disciplinato.

## Deploy sul server (via SSH, chiave WSL dedicata da autorizzare)

1. `git clone` in `~/progetti/bigdata-polymarket` (da GitHub quando il repo esiste;
   in alternativa `rsync` diretto).
2. `docker compose -f deploy/docker-compose.yml up -d --build`
3. Route tunnel: aggiungere `polymarket.massimomarrone.dev → http://polymarket-site:80`
   alla config di cloudflared (ingress) + record DNS CNAME (se il tunnel è
   dashboard-managed si fa da Cloudflare Zero Trust UI; da verificare sul server).
4. Verifica esterna: `curl -I https://polymarket.massimomarrone.dev` + smoke delle 5 route.

## Rischi e mitigazioni

- **Streamlit dietro proxy**: serve `--server.baseUrlPath=/app` e WebSocket nel proxy;
  testato con smoke esterno prima di dichiarare fatto.
- **RAM**: il container dashboard con duckdb+pandas sta sotto i 500MB; il server ha 10GB liberi.
- **Dati nel repo pubblico**: post pubblici Bluesky/Telegram, contenuto accademico; ok.
  Niente credenziali (verificato `git ls-files`).
- **Demo all'orale**: la demo resta LOCALE (non dipendere dalla rete dell'aula);
  il deploy è un plus da mostrare se la rete regge.

## Fuori scope (post-esame)

Webhook CD al push (pattern vocab-massimo), portfolio hub sulla homepage, analytics.
