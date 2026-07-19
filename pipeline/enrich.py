"""Language detection, sentiment and NER over the unique posts of the three platforms.

Enrichment is keyed on the post, not on the (post, contract) pair: a post linked to
three contracts is the same text three times, and scoring it once cuts the work by
a third (45,623 unique posts against 65,159 pairs, three platforms).

Language is DETECTED, not trusted: 17,343 Bluesky posts carry no `langs` field at
all, and Telegram carries none by construction. Non-English posts are kept in the
dataset but flagged, because the sentiment model is English-only — scoring a German
post with an English model produces a number, and that number is meaningless.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "post_enriched.jsonl"

SENTIMENT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"
BATCH = 64


def unique_posts() -> list[dict]:
    seen: set[str] = set()
    posts: list[dict] = []
    for path in (RAW / "bluesky" / "posts.jsonl", RAW / "telegram" / "linked.jsonl",
                 RAW / "reddit" / "posts.jsonl"):
        if not path.exists():
            continue
        for line in path.open():
            p = json.loads(line)
            if p["post_id"] in seen or not p.get("text", "").strip():
                continue
            seen.add(p["post_id"])
            posts.append({"post_id": p["post_id"], "platform": p["platform"],
                          "text": p["text"]})
    return posts


def detect_languages(posts: list[dict]) -> None:
    from langdetect import detect, DetectorFactory, LangDetectException

    DetectorFactory.seed = 0  # langdetect is stochastic; pin it so runs are reproducible
    for p in posts:
        try:
            p["language"] = detect(p["text"])
        except LangDetectException:
            p["language"] = None  # too short / no letters (emoji-only, links)


def add_sentiment(posts: list[dict]) -> None:
    """Sentiment for English posts only; the model is English-only."""
    from transformers import pipeline

    clf = pipeline("sentiment-analysis", model=SENTIMENT_MODEL,
                   truncation=True, max_length=128, batch_size=BATCH)
    targets = [p for p in posts if p["language"] == "en"]
    texts = [p["text"][:500] for p in targets]
    print(f"sentiment su {len(targets)} post inglesi...", flush=True)

    for i in range(0, len(texts), 500):
        chunk = clf(texts[i:i + 500])
        for p, r in zip(targets[i:i + 500], chunk):
            label = r["label"].lower()
            p["sentiment"] = label
            # Signed score: negative posts get a negative number, so a daily mean
            # is directly interpretable as "how the crowd felt that day".
            p["sentiment_score"] = (r["score"] if label == "positive"
                                    else -r["score"] if label == "negative" else 0.0)
        if i % 5000 == 0:
            print(f"  {i}/{len(texts)}", flush=True)


def add_entities(posts: list[dict]) -> None:
    import spacy

    nlp = spacy.load("en_core_web_sm", disable=["lemmatizer", "tagger"])
    targets = [p for p in posts if p["language"] == "en"]
    texts = [p["text"][:500] for p in targets]
    print(f"NER su {len(targets)} post...", flush=True)

    for p, doc in zip(targets, nlp.pipe(texts, batch_size=BATCH)):
        p["entities"] = [{"text": e.text, "label": e.label_} for e in doc.ents
                         if e.label_ in ("PERSON", "ORG", "GPE", "LOC", "EVENT")]


def main() -> None:
    posts = unique_posts()
    print(f"{len(posts)} post unici")

    detect_languages(posts)
    n_en = sum(p["language"] == "en" for p in posts)
    print(f"inglesi: {n_en} ({100*n_en/len(posts):.0f}%) — gli altri restano ma "
          f"senza sentiment")

    add_sentiment(posts)
    add_entities(posts)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        for p in posts:
            p.pop("text")  # the text lives in posts.parquet; this file is enrichment
            f.write(json.dumps(p) + "\n")

    scored = [p for p in posts if "sentiment" in p]
    from collections import Counter
    print(f"\n{len(scored)} post con sentiment -> {OUT}")
    print("distribuzione:", Counter(p["sentiment"] for p in scored).most_common())
    ents = Counter(e["text"] for p in posts for e in p.get("entities", []))
    print("entità più citate:", ents.most_common(8))


if __name__ == "__main__":
    main()
