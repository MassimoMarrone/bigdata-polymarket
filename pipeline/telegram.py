"""Collect messages from public Telegram channels over the contracts' lifetime.

Deliberately NOT a per-contract search. We pull the channels' full history in the
window and link offline with the same funnel used for Bluesky (keyword -> embedding
-> judge). Using one linking method across both platforms is what makes the
cross-platform comparison of Task 2.4 interpretable: any difference we find is a
property of the platforms, not of two different linking heuristics.

Channels are news broadcasters, so the "discourse" here is information flow with
engagement (views, forwards, reactions) rather than user opinion — that contrast
is the point.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from telethon.sync import TelegramClient

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "telegram" / "messages.jsonl"
CONTRACTS = ROOT / "data" / "raw" / "polymarket" / "contracts.jsonl"

CHANNELS = {
    "politics": ["disclosetv", "insiderpaper", "bnonews"],  # thespectatorindex: morto dal 2020
    "finance": ["WatcherGuru", "financialjuice", "Cointelegraph", "unfolded"],
    "sports": ["ESPN", "onefootball"],
}


def env(key: str) -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.strip().startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip("'\"")
    raise SystemExit(f"{key} mancante in .env")


def window() -> tuple[datetime, datetime]:
    """The span the contracts actually cover — no point fetching outside it."""
    dates = []
    for line in CONTRACTS.open():
        c = json.loads(line)
        for key in ("creation_date", "close_date"):
            dates.append(datetime.fromisoformat(c[key].replace("Z", "+00:00")))
    return min(dates), max(dates)


def done_channels() -> set[str]:
    if not OUT.exists():
        return set()
    with OUT.open() as f:
        return {json.loads(line)["channel"] for line in f}


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    start, end = window()
    print(f"finestra: {start:%Y-%m-%d} -> {end:%Y-%m-%d}")

    already = done_channels()
    client = TelegramClient(str(ROOT / "tg.session"),
                            int(env("TG_API_ID")), env("TG_API_HASH"))
    total = 0
    with client, OUT.open("a") as f:
        for domain, channels in CHANNELS.items():
            for name in channels:
                if name in already:
                    print(f"{name:20s} gia' raccolto, skip")
                    continue
                n = 0
                for msg in client.iter_messages(name, offset_date=end, reverse=False):
                    ts = msg.date.astimezone(timezone.utc)
                    if ts < start:
                        break  # walked past the window, older messages are useless
                    if not msg.message:
                        continue  # media-only post, no text to analyse
                    reactions = 0
                    if msg.reactions and msg.reactions.results:
                        reactions = sum(r.count for r in msg.reactions.results)
                    f.write(json.dumps({
                        "post_id": f"{name}/{msg.id}",
                        "platform": "telegram",
                        "url": f"https://t.me/{name}/{msg.id}",
                        "channel": name,
                        "channel_domain": domain,
                        "collected_at": datetime.now(timezone.utc).isoformat(),
                        "author_id": name,
                        "author_name": name,
                        "author_url": f"https://t.me/{name}",
                        "published_at": ts.isoformat(),
                        "text": msg.message,
                        "language": None,  # detected in preprocessing
                        "view_count": msg.views or 0,
                        "repost_count": msg.forwards or 0,
                        "like_count": reactions,
                        "reply_count": msg.replies.replies if msg.replies else 0,
                    }) + "\n")
                    n += 1
                    if n % 2000 == 0:
                        print(f"  {name}: {n} messaggi...", flush=True)
                total += n
                print(f"{name:20s} {n:6d} messaggi", flush=True)

    print(f"\n{total} messaggi -> {OUT}")


if __name__ == "__main__":
    main()
