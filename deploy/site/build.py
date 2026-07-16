"""Static site generator: content/*.md -> dist/.

Runs inside the nginx image build (multi-stage), so the server needs no Python.
Local preview:  python3 deploy/site/build.py && python3 -m http.server -d deploy/site/dist
"""
from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
CONTENT = HERE / "content"
TEMPLATE = HERE / "template"
DIST = HERE / "dist"

PAGES = {
    # slug -> (source md, page title, lang, badge shown above the document)
    "report": ("relazione.md", "Relazione tecnica", "it",
               "🇮🇹 Documento in italiano — technical report, in Italian"),
    "decisions": ("decisioni.md", "Log delle decisioni", "it",
                  "🇮🇹 Documento in italiano — 16 argued decisions, in Italian"),
    "setup": ("setup.md", "Setup & architecture", "en", "🇬🇧 English"),
}

MD_EXT = ["tables", "fenced_code", "toc", "sane_lists"]

# fenced_code rende ```mermaid come <pre><code class="language-mermaid">, con il
# sorgente HTML-escaped. mermaid.js vuole <pre class="mermaid"> e il testo grezzo
# (i diagrammi contengono <br/> e <b>, che vanno riconsegnati non escaped).
MERMAID_RE = re.compile(
    r'<pre><code class="language-mermaid">(.*?)</code></pre>', re.DOTALL)

# I sorgenti sono note di Obsidian: hanno un frontmatter YAML che non e'
# contenuto e che altrimenti finisce in pagina come "tags: [] date created: ...".
FRONTMATTER_RE = re.compile(r'\A---\n.*?\n---\n', re.DOTALL)


def strip_frontmatter(text: str) -> str:
    return FRONTMATTER_RE.sub('', text, count=1)


def unwrap_mermaid(body: str) -> str:
    return MERMAID_RE.sub(
        lambda m: f'<pre class="mermaid">{html.unescape(m.group(1))}</pre>', body)


def nav_classes(active: str) -> dict[str, str]:
    return {f"active_{name}": "active" if name == active else ""
            for name in ("overview", "report", "decisions", "setup")}


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    shutil.copy(TEMPLATE / "index.html", DIST / "index.html")
    shutil.copy(TEMPLATE / "style.css", DIST / "style.css")
    shutil.copytree(CONTENT / "shots", DIST / "shots")
    # mermaid.js e' vendorizzato, non da CDN: la demo dell'orale deve reggere
    # anche senza rete verso jsdelivr.
    shutil.copytree(TEMPLATE / "vendor", DIST / "vendor")

    page_tpl = (TEMPLATE / "page.html").read_text(encoding="utf-8")
    for slug, (src, title, lang, badge) in PAGES.items():
        raw = strip_frontmatter((CONTENT / src).read_text(encoding="utf-8"))
        body = unwrap_mermaid(markdown.markdown(raw, extensions=MD_EXT))
        page = page_tpl.format(content=body, title=title, lang=lang,
                               langnote=badge, **nav_classes(slug))
        out = DIST / slug / "index.html"
        out.parent.mkdir(parents=True)
        out.write_text(page, encoding="utf-8")
        n = body.count('<pre class="mermaid">')
        print(f"  {slug}/index.html  <- {src}" + (f"  ({n} diagrammi)" if n else ""))

    print(f"dist pronto: {DIST}")


if __name__ == "__main__":
    main()
