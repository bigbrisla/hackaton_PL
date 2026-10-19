"""Pulse live server: match replay -> engine -> agent newsroom -> WebSocket, plus the MCP endpoint.

    uv run uvicorn engine.server:app --reload

GET  /api/matches                      demo fixtures
GET  /api/matches/{match_id}/meta      teams, rosters, venue
WS   /ws/matches/{match_id}?speed=20&start_minute=0&langs=en,it&focus_player=HRV-11
     messages: meta, event, overlay, moment, state, agent_trace, story
POST /mcp                              MCP streamable HTTP (tools over running sessions)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import uuid
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agents.llm import online
from agents.pipeline import Newsroom
from generator.replay import live_feed
from generator.simulate import simulate

from . import speech
from .core import MatchEngine
from .mcp_server import SESSIONS, mcp

DEMO_FIXTURES = [("NBR", "HRV", 7), ("KMT", "ASV", 3), ("CLW", "SWC", 11)]
NEWSROOM_MIN_PRIORITY = 45
STALE_AFTER_S = 240.0  # match seconds: older moments are dropped unless they are goals or recaps
CACHE_DIR = Path(os.getenv("PULSE_CACHE_DIR", Path(__file__).parent.parent / "data" / "stories"))


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Pulse match intelligence", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/mcp", mcp.streamable_http_app())


@lru_cache(maxsize=16)
def load_match(match_id: str) -> tuple[dict, list[dict]]:
    try:
        home, away, seed = match_id.split("-")
        meta, events = simulate(home, away, int(seed))
    except (ValueError, KeyError) as exc:
        raise HTTPException(404, f"unknown match {match_id}") from exc
    return meta, [e.to_dict() for e in events]


def cache_path(match_id: str, moment: dict, langs: list[str], focus: str | None) -> Path:
    # keyed on the source event and moment type, which stay stable when the engine evolves
    return CACHE_DIR / match_id / f"{moment['source_event']}__{moment['type']}__{'-'.join(langs)}__{focus or 'none'}.json"


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "model": "foundry" if online() else "offline", "sessions": len(SESSIONS)}


@app.get("/api/matches")
def matches() -> list[dict]:
    out = []
    for home, away, seed in DEMO_FIXTURES:
        meta, _ = load_match(f"{home}-{away}-{seed}")
        out.append({"match_id": meta["match_id"], "home": meta["home"]["name"], "away": meta["away"]["name"],
                    "venue": meta["venue"], "kickoff": meta["kickoff"]})
    return out


@app.get("/api/matches/{match_id}/meta")
def match_meta(match_id: str) -> dict:
    return load_match(match_id)[0]


@app.get("/api/sessions/{session_id}/players/{player_id}")
def session_player(session_id: str, player_id: str) -> dict:
    engine = SESSIONS.get(session_id)
    if engine is None or player_id not in engine.players:
        raise HTTPException(404, "unknown session or player")
    return engine.player_summary(player_id)


@app.get("/api/tts")
async def tts(text: str, lang: str = "en") -> Response:
    """Neural narration via Azure AI Speech (keyless). 503 lets the browser fall back to its own voice."""
    if len(text) > 600:
        raise HTTPException(413, "text too long")
    audio = await speech.synthesize(text, lang)
    if audio is None:
        raise HTTPException(503, "speech not configured")
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})


class Session:
    """One viewer connection: engine state, newsroom queue and the socket."""

    def __init__(self, ws: WebSocket, meta: dict, langs: list[str], focus_player: str | None):
        self.ws, self.meta, self.langs, self.focus = ws, meta, langs, focus_player
        self.id = uuid.uuid4().hex[:12]
        self.engine = MatchEngine(meta)
        self.queue: asyncio.Queue[dict] = asyncio.Queue()
        self.send_lock = asyncio.Lock()
        mcp_url = os.getenv("PULSE_MCP_URL")
        self.newsroom = Newsroom(self.engine, langs, focus_player, on_trace=self.on_trace,
                                 mcp_url=mcp_url, session_id=self.id)

    async def send(self, msg: dict) -> None:
        async with self.send_lock:
            await self.ws.send_json(msg)

    async def on_trace(self, item: dict) -> None:
        await self.send({"kind": "agent_trace", **item})

    async def newsroom_worker(self) -> None:
        while True:
            moment = await self.queue.get()
            now = self.engine.last_ev["ts"] if self.engine.last_ev else moment["ts"]
            if now - moment["ts"] > STALE_AFTER_S and moment["priority"] < 90:
                await self.on_trace({"moment_id": moment["moment_id"], "agent": "producer",
                                     "status": "dropped_stale", "ms": 0, "detail": "the match has moved on"})
                continue
            path = cache_path(self.meta["match_id"], moment, self.langs, self.focus)
            if path.exists():
                story = json.loads(path.read_text())
                story.update(cached=True, moment_id=moment["moment_id"])
                for t in story.get("trace", []):
                    t["moment_id"] = moment["moment_id"]
                for t in story.get("trace", []):  # replay the hand-offs so the newsroom panel shows them
                    await self.on_trace({**t, "detail": t.get("detail", ""), "cached": True})
            else:
                story = await self.newsroom.cover(moment)
                if online():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(story))
            await self.send(story)


@app.websocket("/ws/matches/{match_id}")
async def stream(ws: WebSocket, match_id: str, speed: float = 20.0, start_minute: float = 0.0,
                 langs: str = "en", focus_player: str | None = None) -> None:
    await ws.accept()
    try:
        meta, events = load_match(match_id)
    except HTTPException:
        await ws.close(code=4404)
        return
    session = Session(ws, meta, [lang for lang in langs.split(",") if lang] or ["en"], focus_player)
    SESSIONS[session.id] = session.engine
    # start_minute is the broadcast clock (first-half added time does not shift the second half)
    period = 1 if start_minute < 45 else 2
    start_ts = next((e["ts"] for e in events if e["period"] == period and e["minute"] >= start_minute and e["minute"] > 0),
                    0.0) if start_minute > 0 else 0.0
    warm = [e for e in events if e["ts"] < start_ts]
    for ev in warm:  # fast-forward silently so stats and Chaos Index are warm at the start minute
        session.engine.ingest(ev)
    worker = asyncio.create_task(session.newsroom_worker())
    try:
        await session.send({"kind": "meta", "meta": meta, "start_ts": start_ts, "session_id": session.id,
                            "model": "foundry" if online() else "offline"})
        if warm:  # joining mid-match: hand over the state built while fast-forwarding
            e = session.engine
            await session.send({"kind": "bootstrap", "state": e.snapshot(warm[-1]),
                                "chaos_series": [{"ts": ts, "chaos": c} for ts, c in e.chaos_series],
                                "moments": e.moments})
        async for ev in live_feed(events[len(warm):], speed):
            for msg in session.engine.ingest(ev):
                await session.send(msg)
                if msg["kind"] == "moment" and msg["priority"] >= NEWSROOM_MIN_PRIORITY:
                    session.queue.put_nowait(msg)
            await asyncio.sleep(0)
        while not session.queue.empty():  # let the newsroom finish the last stories (recap)
            await asyncio.sleep(0.5)
        await asyncio.sleep(1)
        await session.send({"kind": "end"})
        await ws.close()
    except WebSocketDisconnect:
        pass
    finally:
        worker.cancel()
        SESSIONS.pop(session.id, None)


# production: the built frontend is served by the same app (single container)
WEB_DIST = Path(__file__).parent.parent / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
