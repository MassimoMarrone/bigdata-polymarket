"""Valida il linking su Reddit: giudice Gemini su un campione stratificato di post
Reddit, poi Cohen's kappa fra filtro semantico (MPNet@0.35) e giudice.
Completa la validazione del linking per la 3a piattaforma (Bluesky+Telegram gia' fatti).

    python3 pipeline/reddit_kappa.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from linking import judge, env, THRESHOLD  # riusa la logica gia' scritta e validata

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
N = 200


def cohen_kappa(a: list[int], b: list[int]) -> float:
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pa1 = sum(a) / n; pb1 = sum(b) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    return (po - pe) / (1 - pe) if pe != 1 else 0.0


def main() -> None:
    contracts = {c["market_id"]: c for c in
                 map(json.loads, (RAW / "polymarket" / "contracts.jsonl").open())}
    posts = {p["post_id"]: p for p in
             (json.loads(l) for l in (RAW / "reddit" / "posts.jsonl").open() if l.strip())}
    scores = [json.loads(l) for l in (PROC / "post_scores.jsonl").open()]
    rdt = [s for s in scores if s["post_id"] in posts and s.get("sim_mpnet") is not None]
    print(f"{len(rdt)} post Reddit con score")

    # campione stratificato lungo la similarita' (come nel linking originale)
    random.seed(42)
    rdt.sort(key=lambda s: s["sim_mpnet"])
    step = max(1, len(rdt) // N)
    sample = rdt[::step][:N]
    pairs = [(contracts[s["market_id"]], posts[s["post_id"]])
             for s in sample if s["market_id"] in contracts]
    sample = [s for s in sample if s["market_id"] in contracts]

    api_key = env("GEMINI_API_KEY")
    print(f"giudice Gemini su {len(pairs)} coppie Reddit...")
    verdicts = judge(pairs, api_key)

    # confronto: filtro (sim>=soglia) vs giudice, solo dove il giudice ha risposto
    filt, jud = [], []
    for s, v in zip(sample, verdicts):
        if v is None:
            continue
        filt.append(1 if s["sim_mpnet"] >= THRESHOLD else 0)
        jud.append(v)
    k = cohen_kappa(filt, jud)
    keep = sum(filt); jkeep = sum(jud)
    print(f"\nvalutate {len(filt)} coppie | filtro tiene {keep}, giudice tiene {jkeep}")
    print(f"Cohen's kappa (Reddit): {k:.3f}")
    out = PROC / "reddit_kappa.json"
    out.write_text(json.dumps({"n": len(filt), "kappa": k,
                               "filter_keep": keep, "judge_keep": jkeep}, indent=2))
    print(f"salvato -> {out}")


if __name__ == "__main__":
    main()
