"""Stage 2, alternative: cross-encoder instead of bi-encoder, evaluated on the same judge sample.

The bi-encoder in linking.py embeds question and post independently and compares two
vectors. A vector can only encode "what this text is about", so the filter matches on the
ENTITY and is blind to the CLAIM: "Villarreal wins the Liga?" scores high against
"Villarreal vs Sevilla: head-to-head stats", because both vectors say "Villarreal, football".
31% of the posts kept at the tuned threshold are noise of exactly this shape.

A cross-encoder reads (question, post) jointly, so attention can relate the post's assertion
to the question's assertion rather than just to its topic. That is the hypothesis under test.
The models are picked to span the two ways of framing the task:

  - ms-marco-*  : trained on MS MARCO passage ranking -> "does this passage answer this
                  query". Closest to our framing (a contract question IS a query), and cheap.
                  Outputs an unbounded logit, not a [0,1] score: the threshold must be
                  searched on the observed range, not assumed.
  - qnli-electra: trained on QNLI -> "does this sentence contain the answer to this question".
                  Explicitly question-vs-claim, which is precisely the distinction the
                  bi-encoder misses.
  - nli-deberta : 3-way NLI (contradiction/entailment/neutral). We take P(entailment) as the
                  score. A post that merely shares the subject is 'neutral', not 'entailment',
                  so in principle this is the sharpest instrument against our false positives.
  - stsb-roberta: semantic textual similarity. Included as a control: it is a cross-encoder,
                  but its objective is *similarity*, the same objective the bi-encoder already
                  optimises. If cross-attention alone were enough, this would win; if the
                  objective is what matters, it should lag the three above.

Ground truth is data/processed/linking_validation.jsonl — the exact 200 (contract, post) pairs
the Gemini judge labelled for the bi-encoder, so every number below is comparable to the
baseline at equal conditions. Success threshold pre-registered before running: Cohen's kappa > 0.55.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

PROC = Path(__file__).resolve().parents[1] / "data" / "processed"
VALIDATION = PROC / "linking_validation.jsonl"

# score_kind: how to turn the model's raw head output into one number per pair.
#   "logit"      -> single unbounded output, use as-is
#   "sigmoid"    -> single output trained with BCE, squashed to [0,1]
#   "entailment" -> 3 logits, take softmax P(entailment)
CROSS_ENCODERS: dict[str, tuple[str, str]] = {
    "ms-marco-L6":   ("cross-encoder/ms-marco-MiniLM-L-6-v2", "logit"),
    "ms-marco-L12":  ("cross-encoder/ms-marco-MiniLM-L-12-v2", "logit"),
    "qnli-electra":  ("cross-encoder/qnli-electra-base", "sigmoid"),
    "nli-deberta":   ("cross-encoder/nli-deberta-v3-base", "entailment"),
    "stsb-roberta":  ("cross-encoder/stsb-roberta-base", "sigmoid"),
}

# Baselines already measured in linking.py; repeated here so the final table is self-contained.
BASELINES = [("bi-mpnet (baseline)", 0.35, 0.434, 0.69, 0.85),
             ("bi-minilm (baseline)", 0.45, 0.410, 0.72, 0.70)]

KAPPA_TARGET = 0.55


def load_pairs() -> list[dict]:
    """The judge-labelled pairs, minus any the judge failed to label."""
    rows = [json.loads(line) for line in VALIDATION.open()]
    return [r for r in rows if r["judge"] is not None]


def score(model_name: str, kind: str, rows: list[dict]) -> np.ndarray:
    """One score per (question, post) pair, higher = more relevant."""
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(model_name, max_length=256)
    pairs = [(r["question"], r["text"]) for r in rows]
    raw = np.asarray(model.predict(pairs, batch_size=32, show_progress_bar=False),
                     dtype=np.float64)

    if kind == "entailment":
        # nli-deberta label order is (contradiction, entailment, neutral).
        e = np.exp(raw - raw.max(axis=1, keepdims=True))
        return (e / e.sum(axis=1, keepdims=True))[:, 1]
    if kind == "sigmoid":
        # These heads already emit [0,1] under sentence-transformers' default activation;
        # clip only guards against a model whose head is left unbounded.
        return raw if raw.min() >= 0.0 and raw.max() <= 1.0 else 1 / (1 + np.exp(-raw))
    return raw


def sweep(scores: np.ndarray, gold: list[int]) -> tuple[float, float, float, float]:
    """Best (threshold, kappa, precision, recall) over the score's *observed* range.

    Candidate thresholds are the midpoints between consecutive observed scores, so this
    works for a [0,1] probability and for an unbounded ms-marco logit alike, without
    hard-coding a grid that might miss the useful region entirely.
    """
    from sklearn.metrics import cohen_kappa_score, precision_score, recall_score

    uniq = np.unique(scores)
    candidates = (uniq[:-1] + uniq[1:]) / 2
    best = (float("nan"), -1.0, 0.0, 0.0)
    for thr in candidates:
        pred = (scores >= thr).astype(int)
        if len(set(pred)) < 2:
            continue
        k = cohen_kappa_score(gold, pred)
        if k > best[1]:
            best = (float(thr), float(k),
                    float(precision_score(gold, pred, zero_division=0)),
                    float(recall_score(gold, pred, zero_division=0)))
    return best


def false_positives(rows: list[dict], scores: np.ndarray, thr: float) -> list[dict]:
    """Pairs the model keeps but the judge rejected — the residual error to inspect."""
    return sorted(
        ({"score": float(s), **r} for r, s in zip(rows, scores)
         if s >= thr and r["judge"] == 0),
        key=lambda r: -r["score"])


def main() -> None:
    rows = load_pairs()
    gold = [r["judge"] for r in rows]
    print(f"{len(rows)} coppie giudicate, {sum(gold)} rilevanti "
          f"({100 * sum(gold) / len(rows):.0f}%)\n")

    results = list(BASELINES)
    detail: dict[str, tuple[np.ndarray, float]] = {}

    for key, (name, kind) in CROSS_ENCODERS.items():
        print(f"scoring {key} ({name})...", flush=True)
        s = score(name, kind, rows)
        thr, k, p, rc = sweep(s, gold)
        print(f"  range osservato [{s.min():.3f}, {s.max():.3f}] "
              f"-> soglia {thr:.3f} kappa {k:.3f}", flush=True)
        results.append((key, thr, k, p, rc))
        detail[key] = (s, thr)

    print(f"\n{'modello':22s} {'soglia':>8s} {'kappa':>7s} {'precision':>10s} {'recall':>7s}")
    print("-" * 58)
    for name, thr, k, p, rc in sorted(results, key=lambda r: -r[2]):
        print(f"{name:22s} {thr:8.3f} {k:7.3f} {p:10.2f} {rc:7.2f}")

    best_ce = max((r for r in results if r[0] in detail), key=lambda r: r[2])
    best_all = max(results, key=lambda r: r[2])
    print(f"\nmigliore cross-encoder: {best_ce[0]} (kappa={best_ce[2]:.3f})")
    print(f"migliore in assoluto:   {best_all[0]} (kappa={best_all[2]:.3f})")
    print(f"soglia pre-registrata kappa > {KAPPA_TARGET}: "
          f"{'SUPERATA' if best_all[2] > KAPPA_TARGET else 'NON SUPERATA'}")

    s, thr = detail[best_ce[0]]
    fps = false_positives(rows, s, thr)
    print(f"\nfalsi positivi di {best_ce[0]} @ {thr:.3f}: {len(fps)}\n")
    for r in fps[:20]:
        print(f"[{r['score']:.3f}] Q: {r['question']}")
        print(f"          P: {r['text'][:150].replace(chr(10), ' ')}\n")


if __name__ == "__main__":
    main()
