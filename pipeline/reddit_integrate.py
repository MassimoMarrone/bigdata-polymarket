"""Integrazione INCREMENTALE di Reddit: calcola solo cio' che manca per i post
Reddit (score MPNet + sentiment + NER) e lo APPENDE ai file esistenti, senza
ri-processare Bluesky/Telegram (che hanno gia' score e enrichment).

Molto piu' veloce del full re-run: 6.5k post × 1 modello invece di 65k × 2.

    python3 pipeline/reddit_integrate.py
poi: python3 pipeline/storage.py && correlation.py && sentiment_direction.py && predict.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
REDDIT = RAW / "reddit" / "posts.jsonl"
CONTRACTS = RAW / "polymarket" / "contracts.jsonl"
SCORES = PROC / "post_scores.jsonl"
ENRICHED = PROC / "post_enriched.jsonl"
MPNET = "all-mpnet-base-v2"


def reddit_posts() -> list[dict]:
    return [json.loads(l) for l in REDDIT.open() if l.strip()]


def already_scored() -> set:
    return {json.loads(l)["post_id"] for l in SCORES.open()} if SCORES.exists() else set()


def already_enriched() -> set:
    return {json.loads(l)["post_id"] for l in ENRICHED.open()} if ENRICHED.exists() else set()


def add_scores(posts: list[dict]) -> None:
    """MPNet cosine post↔domanda del contratto, solo per i post non ancora in post_scores."""
    from sentence_transformers import SentenceTransformer, util
    contracts = {c["market_id"]: c for c in map(json.loads, CONTRACTS.open())}
    done = already_scored()
    todo = [p for p in posts if p["post_id"] not in done and p["market_id"] in contracts]
    if not todo:
        print("score: niente da fare")
        return
    print(f"score MPNet su {len(todo)} post Reddit...")
    model = SentenceTransformer(MPNET)
    q_by_market = {mid: c["question"] for mid, c in contracts.items()}
    # embedding domande una volta
    mids = list(q_by_market)
    q_emb = dict(zip(mids, model.encode([q_by_market[m] for m in mids],
                                        convert_to_tensor=True, batch_size=64)))
    p_emb = model.encode([p["text"] for p in todo], convert_to_tensor=True,
                         batch_size=64, show_progress_bar=True)
    with SCORES.open("a") as f:
        for i, p in enumerate(todo):
            sim = float(util.cos_sim(p_emb[i], q_emb[p["market_id"]])[0][0])
            f.write(json.dumps({"post_id": p["post_id"], "market_id": p["market_id"],
                                "sim_minilm": None, "sim_mpnet": sim}) + "\n")
    print(f"score: +{len(todo)} righe in post_scores.jsonl")


def add_enrichment(posts: list[dict]) -> None:
    """Lingua + sentiment (RoBERTa) + NER (spaCy) sui post Reddit unici non arricchiti."""
    from langdetect import detect, DetectorFactory, LangDetectException
    DetectorFactory.seed = 0
    done = already_enriched()
    seen, todo = set(), []
    for p in posts:
        pid = p["post_id"]
        if pid in done or pid in seen or not p.get("text", "").strip():
            continue
        seen.add(pid)
        todo.append({"post_id": pid, "platform": "reddit", "text": p["text"]})
    if not todo:
        print("enrich: niente da fare")
        return
    for p in todo:
        try:
            p["language"] = detect(p["text"])
        except LangDetectException:
            p["language"] = "unknown"
    en = [p for p in todo if p["language"] == "en"]
    print(f"enrich: {len(todo)} post Reddit, {len(en)} inglesi")

    from transformers import pipeline
    clf = pipeline("sentiment-analysis",
                   model="cardiffnlp/twitter-roberta-base-sentiment-latest",
                   truncation=True, max_length=128, batch_size=32)
    texts = [p["text"][:500] for p in en]
    for i in range(0, len(texts), 500):
        for p, r in zip(en[i:i + 500], clf(texts[i:i + 500])):
            lab = r["label"].lower()
            p["sentiment"] = lab
            p["sentiment_score"] = (r["score"] if lab == "positive"
                                    else -r["score"] if lab == "negative" else 0.0)
        print(f"  sentiment {min(i+500, len(texts))}/{len(texts)}")

    import spacy
    nlp = spacy.load("en_core_web_sm", disable=["lemmatizer", "tagger"])
    for p in en:
        doc = nlp(p["text"][:500])
        p["entities"] = [{"text": e.text, "label": e.label_} for e in doc.ents
                         if e.label_ in ("PERSON", "ORG", "GPE")]

    with ENRICHED.open("a") as f:
        for p in todo:
            p.pop("text")
            f.write(json.dumps(p) + "\n")
    print(f"enrich: +{len(todo)} righe in post_enriched.jsonl")


def main() -> None:
    posts = reddit_posts()
    print(f"{len(posts)} post Reddit totali")
    add_scores(posts)
    add_enrichment(posts)
    print("\nFatto. Ora: python3 pipeline/storage.py")


if __name__ == "__main__":
    main()
