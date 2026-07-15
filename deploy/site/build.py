"""Static site generator: content/*.md -> dist/.

Runs inside the nginx image build (multi-stage), so the server needs no Python.
Local preview:  python3 deploy/site/build.py && python3 -m http.server -d deploy/site/dist
"""
from __future__ import annotations

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

    page_tpl = (TEMPLATE / "page.html").read_text(encoding="utf-8")
    for slug, (src, title, lang, badge) in PAGES.items():
        body = markdown.markdown((CONTENT / src).read_text(encoding="utf-8"),
                                 extensions=MD_EXT)
        html = page_tpl.format(content=body, title=title, lang=lang,
                               langnote=badge, **nav_classes(slug))
        out = DIST / slug / "index.html"
        out.parent.mkdir(parents=True)
        out.write_text(html, encoding="utf-8")
        print(f"  {slug}/index.html  <- {src}")

    print(f"dist pronto: {DIST}")


if __name__ == "__main__":
    main()
