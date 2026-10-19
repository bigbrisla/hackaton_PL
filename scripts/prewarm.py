"""Pre-generate the newsroom's verified stories for a demo match, so replays are instant and free.

    uv run python -m scripts.prewarm --match NBR-HRV-7 --langs en,it,es,ja [--focus HRV-11] [--from-minute 70]

Each key moment is covered against a snapshot of the engine taken at that moment (so agents see the
match exactly as it stood live), several moments in parallel.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import time

from agents.llm import online
from agents.pipeline import Newsroom
from engine.server import NEWSROOM_MIN_PRIORITY, cache_path, load_match
from engine.core import MatchEngine


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--match", default="NBR-HRV-7")
    ap.add_argument("--langs", default="en,it,es,ja")
    ap.add_argument("--focus", default=None)
    ap.add_argument("--from-minute", type=int, default=0)
    ap.add_argument("--parallel", type=int, default=4)
    args = ap.parse_args()
    if not online():
        raise SystemExit("FOUNDRY_PROJECT_ENDPOINT is not set: nothing to pre-generate")
    langs = args.langs.split(",")
    meta, events = load_match(args.match)
    engine = MatchEngine(meta)
    jobs = []
    for ev in events:
        for msg in engine.ingest(ev):
            if msg["kind"] == "moment" and msg["priority"] >= NEWSROOM_MIN_PRIORITY and ev["minute"] >= args.from_minute:
                path = cache_path(args.match, msg, langs, args.focus)
                if not path.exists():
                    jobs.append((msg, copy.deepcopy(engine), path))
    print(f"{len(jobs)} moments to cover")
    sem = asyncio.Semaphore(args.parallel)
    done = 0

    async def cover(moment, snapshot, path):
        nonlocal done
        async with sem:
            t = time.time()
            story = await Newsroom(snapshot, langs, args.focus).cover(moment)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(story))
            done += 1
            statuses = ",".join(f"{x['agent'][:4]}:{x['status']}" for x in story["trace"])
            print(f"[{done}/{len(jobs)}] {moment['clock']:>6} {moment['type']:<15} {time.time() - t:5.1f}s {statuses}")

    await asyncio.gather(*(cover(*j) for j in jobs))


if __name__ == "__main__":
    asyncio.run(main())
