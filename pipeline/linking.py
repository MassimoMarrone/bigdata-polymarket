"""Stage 2+3 of the linking funnel: semantic filter, validated by an LLM judge.

Keyword retrieval (stage 1) is deliberately high-recall and low-precision: three
distinct WTI contracts ("hit $100?", "$105?", "$30?") all collapse to the query
"WTI Crude Oil" and therefore pull the same posts. Stage 2 scores every retrieved
post against the contract question with a sentence embedding and keeps the ones
above a similarity threshold.

The threshold is not guessed: stage 3 has Gemini judge a stratified sample of
(contract, post) pairs, and we report agreement (Cohen's kappa) between the
embedding filter and the judge. That agreement is the number the report cites,
and it is what lets us compare embedding models on equal terms.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

import requests

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
PROC = Path(__file__).resolve().parents[1] / "data" / "processed"
CONTRACTS = RAW / "polymarket" / "contracts.jsonl"
POSTS = RAW / "bluesky" / "posts.jsonl"
TELEGRAM = RAW / "telegram" / "linked.jsonl"
REDDIT = RAW / "reddit" / "posts.jsonl"

MODELS = {
    "minilm": "sentence-transformers/all-MiniLM-L6-v2",       # fast baseline
    "mpnet": "sentence-transformers/all-mpnet-base-v2",       # stronger, slower
}
THRESHOLD = 0.35  # cosine similarity; calibrated against the judge, see report()

# gemini-2.5-flash's free-tier quota is too small for a few hundred judgements;
# flash-lite answers in ~1.5s with plenty of headroom.
GEMINI = ("https://generativelanguage.googleapis.com/v1beta/models/"
          "gemini-flash-lite-latest:generateContent")
JUDGE_SAMPLE = 200  # (contract, post) pairs sent to the judge


def env(key: str) -> str | None:
    dotenv = Path(__file__).resolve().parents[1] / ".env"
    if dotenv.exists():
        for line in dotenv.read_text().splitlines():
            if line.strip().startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None


def load() -> tuple[dict[str, dict], list[dict]]:
    """Contracts, and every (post, contract) candidate from both platforms.

    All files are already keyword-linked — Bluesky server-side at collection,
    Telegram locally in link_telegram.py, Reddit by search query in
    reddit_collect.py — so the semantic filter below sees the same kind of input
    from each, which is the point.
    """
    contracts = {c["market_id"]: c for c in map(json.loads, CONTRACTS.open())}
    posts: list[dict] = []
    for path in (POSTS, TELEGRAM, REDDIT):
        if path.exists():
            posts.extend(json.loads(line) for line in path.open())
    # A contract may have been dropped by a re-collection; its posts are stale.
    return contracts, [p for p in posts if p["market_id"] in contracts]


def score(model_key: str, contracts: dict, posts: list[dict]) -> list[float]:
    """Cosine similarity between each post and the question of its contract."""
    from sentence_transformers import SentenceTransformer, util

    model = SentenceTransformer(MODELS[model_key])
    questions = {mid: c["question"] for mid, c in contracts.items()}
    q_emb = {mid: e for mid, e in zip(
        questions, model.encode(list(questions.values()), convert_to_tensor=True,
                                batch_size=64, show_progress_bar=False))}

    texts = [p["text"] for p in posts]
    p_emb = model.encode(texts, convert_to_tensor=True, batch_size=64,
                         show_progress_bar=True)
    return [float(util.cos_sim(p_emb[i], q_emb[p["market_id"]])[0][0])
            for i, p in enumerate(posts)]


def judge(pairs: list[tuple[dict, dict]], api_key: str) -> list[int | None]:
    """Gemini's zero-shot relevance verdict per (contract, post) pair: 1, 0, or None."""
    verdicts: list[int | None] = []
    for contract, post in pairs:
        prompt = (
            "You are labelling data for a study linking social media posts to "
            "prediction-market contracts.\n\n"
            f"CONTRACT QUESTION: {contract['question']}\n"
            f"POST: {post['text'][:600]}\n\n"
            "Is this post relevant to that specific contract question — i.e. does it "
            "discuss the same event or outcome, such that its sentiment or volume "
            "could plausibly inform the market's implied probability?\n"
            "Being about the same broad topic is NOT enough: a post about oil prices "
            "in general is NOT relevant to a contract about oil hitting a SPECIFIC "
            "threshold, unless it bears on that threshold.\n\n"
            "Answer with exactly one word: RELEVANT or IRRELEVANT."
        )
        verdict = None
        for attempt in range(6):
            try:
                r = requests.post(
                    GEMINI,
                    headers={"x-goog-api-key": api_key,
                             "Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": prompt}]}],
                          "generationConfig": {
                              "temperature": 0,
                              "maxOutputTokens": 16,
                              # Without this, 2.5-flash spends the output budget on
                              # reasoning tokens and returns an empty answer.
                              "thinkingConfig": {"thinkingBudget": 0}}},
                    timeout=60)
                if r.status_code in (429, 503):
                    time.sleep(5 * (attempt + 1))
                    continue
                if not r.ok:
                    time.sleep(3)
                    continue
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"].upper()
                verdict = 1 if "IRRELEVANT" not in text and "RELEVANT" in text else 0
                break
            except Exception:
                time.sleep(3)
        verdicts.append(verdict)
        if len(verdicts) % 25 == 0:
            ok = sum(v is not None for v in verdicts)
            print(f"  giudice: {len(verdicts)}/{len(pairs)} ({ok} validi)", flush=True)
        time.sleep(1.2)
    return verdicts


def main() -> None:
    PROC.mkdir(parents=True, exist_ok=True)
    contracts, posts = load()
    print(f"{len(posts)} post su {len(contracts)} contratti")

    scores = {k: score(k, contracts, posts) for k in MODELS}

    # Stratified sample across the similarity range, so the judge sees both
    # confident keeps and confident drops, not just borderline cases.
    random.seed(42)
    ranked = sorted(range(len(posts)), key=lambda i: scores["minilm"][i])
    step = max(1, len(ranked) // JUDGE_SAMPLE)
    idx = ranked[::step][:JUDGE_SAMPLE]
    pairs = [(contracts[posts[i]["market_id"]], posts[i]) for i in idx]

    api_key = env("GEMINI_API_KEY")
    print(f"giudice Gemini su {len(pairs)} coppie...")
    verdicts = judge(pairs, api_key)

    rows = []
    for j, i in enumerate(idx):
        rows.append({
            "market_id": posts[i]["market_id"],
            "post_id": posts[i]["post_id"],
            "question": contracts[posts[i]["market_id"]]["question"],
            "text": posts[i]["text"][:300],
            "judge": verdicts[j],
            **{f"sim_{k}": scores[k][i] for k in MODELS},
        })
    with (PROC / "linking_validation.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    with (PROC / "post_scores.jsonl").open("w") as f:
        for i, p in enumerate(posts):
            f.write(json.dumps({
                "post_id": p["post_id"], "market_id": p["market_id"],
                **{f"sim_{k}": scores[k][i] for k in MODELS},
            }) + "\n")

    report(rows)


def report(rows: list[dict]) -> None:
    """Agreement between each embedding filter and the judge, over thresholds."""
    from sklearn.metrics import cohen_kappa_score, precision_score, recall_score

    labelled = [r for r in rows if r["judge"] is not None]
    n_rel = sum(r["judge"] for r in labelled)
    print(f"\ngiudice: {len(labelled)}/{len(rows)} coppie valutate, {n_rel} rilevanti "
          f"({100*n_rel/max(1,len(labelled)):.0f}%)")

    if len(labelled) < 50:
        print("\n!!! ATTENZIONE: troppi pochi verdetti validi. Il kappa qui sotto NON e'\n"
              "!!! statisticamente utilizzabile — non riportarlo nella relazione.\n")

    print(f"\n{'modello':8s} {'soglia':>7s} {'kappa':>7s} {'precision':>10s} {'recall':>7s}")
    best = None
    for model_key in MODELS:
        for thr in (0.25, 0.30, 0.35, 0.40, 0.45, 0.50):
            pred = [int(r[f"sim_{model_key}"] >= thr) for r in labelled]
            gold = [r["judge"] for r in labelled]
            if len(set(pred)) < 2:
                continue
            k = cohen_kappa_score(gold, pred)
            p = precision_score(gold, pred, zero_division=0)
            rc = recall_score(gold, pred, zero_division=0)
            print(f"{model_key:8s} {thr:7.2f} {k:7.3f} {p:10.2f} {rc:7.2f}")
            if best is None or k > best[0]:
                best = (k, model_key, thr)
    if best:
        print(f"\nmigliore: {best[1]} @ soglia {best[2]} (kappa={best[0]:.3f})")


if __name__ == "__main__":
    main()
