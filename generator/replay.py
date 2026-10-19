"""Replay a saved synthetic match as a live feed, paced on event timestamps.

    python -m generator.replay data/NBR-HRV-7.events.jsonl --speed 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import AsyncIterator, Iterable
from pathlib import Path


def load_events(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


async def live_feed(events: Iterable[dict], speed: float = 1.0) -> AsyncIterator[dict]:
    """Yield events with real-time gaps divided by `speed` (speed <= 0 means no pacing)."""
    last_ts = None
    for ev in events:
        if last_ts is not None and speed > 0:
            gap = max(0.0, ev["ts"] - last_ts) / speed
            if gap:
                await asyncio.sleep(gap)
        last_ts = ev["ts"]
        yield ev


def describe(ev: dict) -> str:
    clock = f"{ev['minute']}'" + (f"+{ev['added_minute']}" if ev["added_minute"] else "")
    extra = ev["outcome"] or ev["attrs"].get("kind") or ""
    return f"{clock:>6} {ev['type']:<15} {ev['team_id'] or '':<4} {ev['player_id'] or '':<7} {extra}"


async def _main(path: Path, speed: float, skip_physical: bool) -> None:
    async for ev in live_feed(load_events(path), speed):
        if skip_physical and ev["type"] == "physical_update":
            continue
        print(describe(ev), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("events", type=Path)
    ap.add_argument("--speed", type=float, default=10.0)
    ap.add_argument("--physical", action="store_true", help="also print physical_update events")
    args = ap.parse_args()
    asyncio.run(_main(args.events, args.speed, not args.physical))


if __name__ == "__main__":
    main()
