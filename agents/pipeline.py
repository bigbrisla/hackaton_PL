"""The newsroom: a Microsoft Agent Framework workflow that turns an engine moment into a verified,
personalized, localized and timed broadcast cue.

    Analyst ──► Tactician ──► Storyteller ──► Verifier ──► Localizer ──► Producer ──► cue
       │ (MCP/tools)               ▲              │ problems found (max 2 rewrites)
       │                           └──────────────┘
       └─ skip ─────────────────────────────────────────────────────────────► cue (not aired)

Shared state lives on the Job passed along the graph; each step appends to its trace so the UI can
show the hand-offs live. Any model failure falls back to the role's deterministic responder.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from agent_framework import Agent, Executor, WorkflowBuilder, WorkflowContext, handler
from pydantic import BaseModel

from engine.core import MatchEngine

from . import roles
from .llm import make_client
from .schemas import Brief, Explanation, Localized, Story
from .tools import MatchTools
from .verify import allowed_numbers, check_text, evidence_names, unsupported_numbers

MAX_REWRITES = 2
REASONING_EFFORT = os.getenv("PULSE_REASONING_EFFORT", "low")  # live latency matters more than depth
MODEL_TIMEOUT_S = 30.0
WORDS_PER_SECOND = 3.0

TraceHook = Callable[[dict], Awaitable[None] | None]


@dataclass
class Job:
    moment: dict
    langs: list[str]
    focus_player: str | None
    brief: dict | None = None
    explanation: dict | None = None
    story: dict | None = None
    feedback: list[str] = field(default_factory=list)
    rewrites: int = 0
    needs_rewrite: bool = False
    texts: dict = field(default_factory=dict)  # persona -> lang -> {headline, body, source, translated}
    trace: list[dict] = field(default_factory=list)


class Newsroom:
    def __init__(self, engine: MatchEngine, langs: list[str] | None = None, focus_player: str | None = None,
                 on_trace: TraceHook | None = None, mcp_url: str | None = None, session_id: str | None = None):
        self.engine = engine
        self.mcp_url, self.session_id = mcp_url, session_id
        self.langs = langs or ["en"]
        self.focus_player = focus_player
        self.on_trace = on_trace
        self.on_air_until = 0.0  # Producer's shared schedule: end of the last story card on screen
        self.agents = {
            "analyst": Agent(make_client(roles.analyst_offline), roles.ANALYST, name="analyst"),
            "tactician": Agent(make_client(roles.tactician_offline), roles.TACTICIAN, name="tactician"),
            "storyteller": Agent(make_client(roles.storyteller_offline), roles.STORYTELLER, name="storyteller"),
            "localizer": Agent(make_client(roles.localizer_offline), roles.LOCALIZER, name="localizer"),
        }
        self.fallbacks = {"analyst": roles.analyst_offline, "tactician": roles.tactician_offline,
                          "storyteller": roles.storyteller_offline, "localizer": roles.localizer_offline}
        self.workflow = self._build()
        self.lock = asyncio.Lock()
        # workflow messages are copied between steps, so live objects stay here, keyed by moment
        self.toolsets: dict[str, MatchTools] = {}

    def tools(self, job: Job) -> MatchTools:
        return self.toolsets[job.moment["moment_id"]]

    # ------------------------------------------------------------------ helpers
    async def trace(self, job: Job, agent: str, status: str, started: float, detail: str = "") -> None:
        item = {"moment_id": job.moment["moment_id"], "agent": agent, "status": status,
                "ms": round((time.perf_counter() - started) * 1000), "detail": detail}
        job.trace.append(item)
        if self.on_trace:
            res = self.on_trace(item)
            if asyncio.iscoroutine(res):
                await res

    async def ask(self, job: Job, role: str, payload: dict, schema: type[BaseModel], tools: list | None = None) -> dict:
        """Run one agent with a validated schema; fall back to its deterministic responder on failure."""
        started = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                self.agents[role].run(json.dumps(payload, default=str), tools=tools,
                                      options={"response_format": schema, "reasoning_effort": REASONING_EFFORT}),
                MODEL_TIMEOUT_S)
            value = response.value
            if value is None:
                raise ValueError("no structured output")
            result = value.model_dump()
            status = "ok"
            detail = ""
        except Exception as exc:  # noqa: BLE001 - any model failure must not stop the broadcast
            result = schema.model_validate(self.fallbacks[role](payload)).model_dump()
            status, detail = "fallback", f"{type(exc).__name__}: {exc}"[:160]
        await self.trace(job, role, status, started, detail)
        return result

    # ------------------------------------------------------------------ workflow
    def _build(self):
        room = self

        class AnalystStep(Executor):
            @handler
            async def run(self, job: Job, ctx: WorkflowContext[Job, dict]) -> None:
                payload = {"moment": job.moment}
                if room.mcp_url and room.session_id:
                    payload["session_id"] = room.session_id
                    try:
                        async with room.tools(job).as_mcp_tool(room.mcp_url) as mcp_tool:
                            job.brief = await room.ask(job, "analyst", payload, Brief, [mcp_tool])
                    except Exception:  # noqa: BLE001 - MCP unreachable: use the in-process tools
                        job.brief = await room.ask(job, "analyst", payload, Brief, room.tools(job).as_agent_tools())
                else:
                    job.brief = await room.ask(job, "analyst", payload, Brief, room.tools(job).as_agent_tools())
                if job.brief["newsworthy"] == "skip" and job.moment["priority"] < 90:
                    await ctx.yield_output(room.cue(job, aired=False))
                else:
                    await ctx.send_message(job)

        class TacticianStep(Executor):
            @handler
            async def run(self, job: Job, ctx: WorkflowContext[Job]) -> None:
                job.explanation = await room.ask(job, "tactician", {
                    "moment": job.moment, "brief": job.brief, "evidence": room.tools(job).ledger}, Explanation)
                await ctx.send_message(job)

        class StorytellerStep(Executor):
            @handler
            async def run(self, job: Job, ctx: WorkflowContext[Job]) -> None:
                focus = job.focus_player or (job.brief or {}).get("focus_player")
                job.story = await room.ask(job, "storyteller", {
                    "moment": job.moment, "brief": job.brief, "explanation": job.explanation,
                    "evidence": room.tools(job).ledger, "personas": roles.personas_for(job.moment, focus),
                    "focus_player": focus, "feedback": job.feedback}, Story)
                await ctx.send_message(job)

        class VerifierStep(Executor):
            @handler
            async def run(self, job: Job, ctx: WorkflowContext[Job]) -> None:
                started = time.perf_counter()
                evidence = (job.moment, room.tools(job).ledger)
                allowed = allowed_numbers(*evidence)
                ids = evidence_names(room.engine.players, *evidence)
                problems: dict[str, list[str]] = {}
                if job.rewrites == 0 and job.explanation:  # the explanation airs too: same grounding rules
                    if check_text(job.explanation["why_it_matters"], allowed, room.engine.players, ids):
                        job.explanation = roles.tactician_offline({"moment": job.moment})
                        await room.trace(job, "verifier", "explanation_replaced", started, "ungrounded explanation")
                for t in job.story["texts"]:
                    found = check_text(f"{t['headline']} {t['body']}", allowed, room.engine.players, ids)
                    if found:
                        problems[t["persona"]] = found
                if problems and job.rewrites < MAX_REWRITES:
                    job.rewrites += 1
                    job.feedback = [f"{p}: {msg}" for p, msgs in problems.items() for msg in msgs]
                    job.needs_rewrite = True
                    await room.trace(job, "verifier", "rejected", started, "; ".join(job.feedback)[:300])
                else:
                    if problems:  # still wrong after rewrites: air the facts, never the unverified text
                        fallback = {t["persona"]: t for t in roles.storyteller_offline({
                            "moment": job.moment, "brief": job.brief, "personas": list(problems)})["texts"]}
                    for t in job.story["texts"]:
                        bad = t["persona"] in problems
                        src = fallback[t["persona"]] if bad else t
                        job.texts[t["persona"]] = {"en": {"headline": src["headline"], "body": src["body"],
                                                          "source": "facts" if bad else "ai", "translated": True}}
                    job.needs_rewrite = False
                    await room.trace(job, "verifier", "approved" if not problems else "replaced_with_facts",
                                     started, f"after {job.rewrites} rewrite(s)")
                await ctx.send_message(job)

        class LocalizerStep(Executor):
            @handler
            async def run(self, job: Job, ctx: WorkflowContext[Job]) -> None:
                targets = [lang for lang in job.langs if lang != "en"]
                if targets:
                    english = [{"persona": p, **{k: v["en"][k] for k in ("headline", "body")}}
                               for p, v in job.texts.items()]
                    # one call per market, in parallel: smaller outputs, fewer omissions, lower latency
                    outs = await asyncio.gather(*(room.ask(job, "localizer", {"texts": english, "langs": [lang]},
                                                           Localized) for lang in targets))
                    by_key = {(t["persona"], t["lang"]): t for out in outs for t in out["texts"]}
                    allowed = allowed_numbers(job.moment, room.tools(job).ledger)
                    for p, versions in job.texts.items():
                        src = versions["en"]
                        for lang in targets:
                            t = by_key.get((p, lang))
                            # translations may spell numbers differently ("thirty seconds" -> "30秒") but every
                            # number they state must still be in the evidence
                            ok = (t is not None and t["body"] != src["body"]
                                  and not unsupported_numbers(t["headline"] + " " + t["body"], allowed))
                            versions[lang] = ({"headline": t["headline"], "body": t["body"], "source": src["source"],
                                               "translated": True} if ok else {**src, "translated": False})
                await ctx.send_message(job)

        class ProducerStep(Executor):
            @handler
            async def run(self, job: Job, ctx: WorkflowContext[Job, dict]) -> None:
                started = time.perf_counter()
                cue = room.cue(job, aired=True)
                await room.trace(job, "producer", "scheduled", started,
                                 f"{cue['overlay']['template']} {cue['overlay']['in_ts']}-{cue['overlay']['out_ts']}")
                cue["trace"] = job.trace
                await ctx.yield_output(cue)

        analyst, tactician, storyteller = AnalystStep("analyst"), TacticianStep("tactician"), StorytellerStep("storyteller")
        verifier, localizer, producer = VerifierStep("verifier"), LocalizerStep("localizer"), ProducerStep("producer")
        return (WorkflowBuilder(name="pulse-newsroom", start_executor=analyst)
                .add_edge(analyst, tactician)
                .add_edge(tactician, storyteller)
                .add_edge(storyteller, verifier)
                .add_edge(verifier, storyteller, condition=lambda job: job.needs_rewrite)
                .add_edge(verifier, localizer, condition=lambda job: not job.needs_rewrite)
                .add_edge(localizer, producer)
                .build())

    def cue(self, job: Job, aired: bool) -> dict[str, Any]:
        m = job.moment
        feature = aired and (job.brief or {}).get("newsworthy") == "feature"
        words = max((len(v["en"]["body"].split()) for v in job.texts.values()), default=8)
        duration = min(14.0, max(6.0, words / WORDS_PER_SECOND + 3))
        in_ts = max(m["ts"] + 2.0, self.on_air_until + 0.5 if feature else m["ts"] + 2.0)
        if aired and feature:
            self.on_air_until = in_ts + duration
        return {
            "kind": "story", "moment_id": m["moment_id"], "type": m["type"], "clock": m["clock"], "ts": m["ts"],
            "team_id": m["team_id"], "player_id": m["player_id"], "where": m.get("where"), "aired": aired,
            "airtime": (job.brief or {}).get("newsworthy"), "angle": (job.brief or {}).get("angle"),
            "explanation": job.explanation, "texts": job.texts,
            "evidence_tools": [e["tool"] for e in self.tools(job).ledger],
            "overlay": {"layer": "story_card" if feature else "lower_third",
                        "template": f"moment_{m['type']}", "in_ts": round(in_ts, 2),
                        "out_ts": round(in_ts + duration, 2), "priority": m["priority"]},
            "trace": job.trace,
        }

    async def cover(self, moment: dict) -> dict:
        async with self.lock:
            self.toolsets[moment["moment_id"]] = MatchTools(self.engine)
            try:
                result = await self.workflow.run(Job(moment=moment, langs=self.langs, focus_player=self.focus_player))
                return result.get_outputs()[-1]
            finally:
                self.toolsets.pop(moment["moment_id"], None)
