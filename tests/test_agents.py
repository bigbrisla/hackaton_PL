import asyncio

import pytest
from agent_framework import Agent

from agents import roles
from agents.llm import OfflineChatClient
from agents.pipeline import Newsroom
from agents.verify import allowed_numbers, check_text, same_numbers
from engine.core import MatchEngine
from generator.simulate import simulate


@pytest.fixture(scope="module")
def match():
    meta, events = simulate("NBR", "HRV", 7)
    engine = MatchEngine(meta)
    moments = [m for e in events for m in engine.ingest(e.to_dict()) if m["kind"] == "moment"]
    return engine, moments


def goal(match):
    return next(m for m in match[1] if m["type"] == "goal")


def test_verifier_catches_invented_numbers_and_players(match):
    engine, _ = match
    m = goal(match)
    allowed = allowed_numbers(m)
    ids = {m["player_id"]}
    assert check_text(f"{m['player']} scores at {m['facts']['shot_speed_kmh']} km/h", allowed, engine.players, ids) == []
    assert check_text("A 137 km/h rocket", allowed, engine.players, ids)
    stranger = next(p for pid, p in engine.players.items() if pid not in ids and p["name"] not in str(m))
    assert check_text(f"{stranger['short_name']} watches on", allowed, engine.players, ids)


def test_translation_must_keep_numbers():
    assert same_numbers("Shot at 112.4 km/h, xG 0.31", "Tiro a 112,4 km/h, xG 0,31")
    assert not same_numbers("Shot at 112.4 km/h", "Tiro a 113 km/h")
    assert same_numbers("It's 3-2 after 33.5s", "スコアは3-2、ビルドアップ33.5s")


def test_newsroom_end_to_end_offline(match, monkeypatch):
    monkeypatch.setenv("PULSE_OFFLINE", "1")
    engine, _ = match
    cue = asyncio.run(Newsroom(engine, langs=["en", "it"]).cover(goal(match)))
    assert cue["aired"] and cue["overlay"]["out_ts"] > cue["overlay"]["in_ts"]
    assert {"casual", "analyst", "accessibility"} <= cue["texts"].keys()
    assert [t["agent"] for t in cue["trace"]] == ["analyst", "tactician", "storyteller", "verifier", "localizer", "producer"]


def test_storyteller_rewrites_after_rejection(match, monkeypatch):
    """First draft invents a number; the verifier sends it back and the corrected draft airs."""
    monkeypatch.setenv("PULSE_OFFLINE", "1")
    engine, _ = match
    room = Newsroom(engine)
    drafts = []

    def storyteller(payload):
        drafts.append(payload["feedback"])
        out = roles.storyteller_offline(payload)
        if not payload["feedback"]:
            out["texts"][0]["body"] += " A 999 km/h strike."
        return out

    room.agents["storyteller"] = Agent(OfflineChatClient(storyteller), roles.STORYTELLER)
    cue = asyncio.run(room.cover(goal(match)))
    assert len(drafts) == 2 and any("999" in f for f in drafts[1])
    assert [t["status"] for t in cue["trace"] if t["agent"] == "verifier"] == ["rejected", "approved"]
    assert all(v["en"]["source"] == "ai" for v in cue["texts"].values())


def test_failing_model_falls_back_to_facts(match, monkeypatch):
    monkeypatch.setenv("PULSE_OFFLINE", "1")
    engine, _ = match
    room = Newsroom(engine)

    def broken(payload):
        raise RuntimeError("model unavailable")

    room.agents["tactician"] = Agent(OfflineChatClient(broken), roles.TACTICIAN)
    cue = asyncio.run(room.cover(goal(match)))
    assert cue["aired"]
    assert next(t for t in cue["trace"] if t["agent"] == "tactician")["status"] == "fallback"
