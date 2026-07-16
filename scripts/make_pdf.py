"""Genera il PDF della relazione da Relazione.md.

Perche' cosi': il documento contiene diagrammi mermaid, che pandoc non sa
renderizzare (e comunque niente pandoc/LaTeX su questa macchina). Qui si
riusa la catena che gia' funziona per il sito — markdown -> HTML -> mermaid
disegnato da un browser vero — e si stampa la pagina in PDF.

Differenza dal sito: il sito e' scuro, un PDF da consegnare e stampare no.
Il template qui e' chiaro, in A4, senza navigazione, e mermaid usa un tema
chiaro (i colori dei nodi finiscono dentro l'SVG, quindi non basta un
foglio di stile per la stampa: va ritematizzato a monte).

Uso:
    python3 scripts/make_pdf.py            # -> Progetto/Relazione.pdf
    python3 scripts/make_pdf.py --out X.pdf
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parents[1]
SITE = HERE / "deploy" / "site"
sys.path.insert(0, str(SITE))
from build import MD_EXT, strip_frontmatter, unwrap_mermaid  # noqa: E402

SRC = HERE.parent / "Relazione.md"
OUT = HERE.parent / "Relazione.pdf"

# Chromium + le sue librerie, installati senza root (vedi ~/.local/share).
CHROME = Path.home() / ".cache/ms-playwright/chromium-1148/chrome-linux/chrome"
LIBS = Path.home() / ".local/share/chromium-deps/lib"

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
:root { --ink:#14181F; --muted:#5B6473; --line:#D6DBE3; --accent:#1F5FBF; }
* { box-sizing: border-box; }
body {
  font-family: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  font-size: 10.2pt; line-height: 1.5; color: var(--ink);
  background: #fff; margin: 0;
}
h1, h2, h3, h4 { font-family: Spectral, Georgia, serif; line-height: 1.25; }
h2 { font-size: 20pt; margin: 0 0 2mm; }
h3 { font-size: 13pt; margin: 8mm 0 2mm; padding-bottom: 1.5mm;
     border-bottom: 1px solid var(--line); break-after: avoid; }
h4 { font-size: 11pt; margin: 5mm 0 1.5mm; color: var(--muted); break-after: avoid; }
p { margin: 0 0 2.5mm; text-align: justify; hyphens: auto; }
ul, ol { margin: 0 0 3mm; padding-left: 5mm; }
li { margin-bottom: 1mm; }
a { color: var(--accent); text-decoration: none; }
strong { font-weight: 600; }
code {
  font-family: "IBM Plex Mono", Consolas, monospace; font-size: 8.8pt;
  background: #F1F3F7; padding: 0.4mm 1mm; border-radius: 1mm;
}
pre { background: #F6F8FA; border: 1px solid var(--line); border-radius: 1.5mm;
      padding: 3mm; overflow: hidden; break-inside: avoid; }
pre code { background: none; font-size: 8.2pt; line-height: 1.4; }
table { width: 100%; border-collapse: collapse; margin: 0 0 3.5mm;
        font-size: 8.8pt; break-inside: avoid; }
th, td { border: 1px solid var(--line); padding: 1.4mm 2mm; text-align: left; }
th { background: #F1F3F7; font-weight: 600; }
hr { border: 0; border-top: 1px solid var(--line); margin: 6mm 0; }
blockquote { margin: 0 0 3mm; padding-left: 3mm; border-left: 2px solid var(--line);
             color: var(--muted); }
/* i diagrammi non devono spezzarsi a meta' fra due pagine */
pre.mermaid { background: none; border: 0; padding: 2mm 0 4mm;
              text-align: center; break-inside: avoid; }
/* Il vincolo che conta e' l'ALTEZZA: un diagramma piu' alto della pagina non
   viene rimpicciolito da Chrome, viene TAGLIATO (e con break-inside:avoid si
   porta dietro anche una pagina bianca). Con width:auto + max-height l'SVG
   scala sul viewBox mantenendo le proporzioni. */
pre.mermaid svg {
  width: auto !important; height: auto !important;
  max-width: 100% !important; max-height: 215mm !important;
}
/* mermaid disegna le etichette come veri <p> in un foreignObject: senza questo
   si prendono il justify + hyphens del corpo del testo e le parole dentro i
   nodi risultano stirate ("LIVELLO    PROCESSED    —"). */
pre.mermaid p, pre.mermaid div, pre.mermaid span {
  text-align: center; hyphens: none; margin: 0;
}
"""

PAGE = """<!doctype html>
<html lang="it"><head><meta charset="utf-8"><title>Relazione</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Spectral:wght@600&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono&display=swap" rel="stylesheet">
<style>%(css)s</style></head><body>
%(body)s
<script src="%(mermaid)s"></script>
<script>
  mermaid.initialize({
    startOnLoad: true, theme: 'base',
    themeVariables: {
      fontFamily: "'IBM Plex Sans', sans-serif", fontSize: '13px',
      background: '#ffffff', primaryColor: '#F1F3F7', primaryTextColor: '#14181F',
      primaryBorderColor: '#1F5FBF', secondaryColor: '#F6F8FA',
      tertiaryColor: '#ffffff', mainBkg: '#F1F3F7', lineColor: '#5B6473',
      textColor: '#14181F', nodeBorder: '#8A94A6',
      clusterBkg: '#FAFBFD', clusterBorder: '#D6DBE3',
      edgeLabelBackground: '#ffffff',
      taskBkgColor: '#E7EDF7', taskTextColor: '#14181F',
      taskTextOutsideColor: '#14181F', taskTextDarkColor: '#14181F',
      activeTaskBkgColor: '#1F5FBF', activeTaskBorderColor: '#1F5FBF',
      doneTaskBkgColor: '#3FA37A', doneTaskBorderColor: '#3FA37A',
      critBkgColor: '#D9534F', critBorderColor: '#D9534F',
      gridColor: '#D6DBE3', sectionBkgColor: '#F6F8FA',
      sectionBkgColor2: '#F1F3F7', altSectionBkgColor: '#ffffff',
      titleColor: '#14181F'
    },
    flowchart: { htmlLabels: true, curve: 'basis' },
    gantt: { barHeight: 22, fontSize: 12, leftPadding: 150 }
  });
</script></body></html>"""


def render_html() -> str:
    raw = strip_frontmatter(SRC.read_text(encoding="utf-8"))
    body = unwrap_mermaid(markdown.markdown(raw, extensions=MD_EXT))
    mermaid = (SITE / "template" / "vendor" / "mermaid.min.js").as_uri()
    return PAGE % {"css": CSS, "body": body, "mermaid": mermaid}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    tmp = HERE / "data" / "_pdf_build.html"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(render_html(), encoding="utf-8")

    os.environ["LD_LIBRARY_PATH"] = f"{LIBS}:{os.environ.get('LD_LIBRARY_PATH', '')}"
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(CHROME), args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(tmp.as_uri(), wait_until="networkidle", timeout=120_000)
        # i diagrammi devono essere DISEGNATI prima di stampare, non solo presenti
        page.wait_for_function(
            "() => document.querySelectorAll('pre.mermaid svg').length ==="
            " document.querySelectorAll('pre.mermaid').length", timeout=60_000)
        page.wait_for_timeout(1500)
        n = page.evaluate("document.querySelectorAll('pre.mermaid svg').length")
        page.pdf(path=str(args.out), format="A4", print_background=True,
                 margin={"top": "18mm", "bottom": "20mm",
                         "left": "16mm", "right": "16mm"},
                 display_header_footer=True,
                 header_template="<div></div>",
                 footer_template=(
                     '<div style="width:100%;font-size:8pt;color:#8A94A6;'
                     'font-family:sans-serif;padding:0 16mm;display:flex;'
                     'justify-content:space-between">'
                     '<span>Massimo Marrone — Big Data Engineering 2025/26, Track 2</span>'
                     '<span class="pageNumber"></span></div>'))
        browser.close()

    tmp.unlink(missing_ok=True)
    kb = args.out.stat().st_size // 1024
    print(f"{args.out}  ({kb} KB, {n} diagrammi disegnati)")


if __name__ == "__main__":
    main()
