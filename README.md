# Pulse — explainable match intelligence for every fan

Microsoft × Premier League "Inside the Game" hackathon project. All data is synthetic;
clubs and players are fictional.

> *One match, a million broadcasts.* Pulse turns live match events into explained, personalized and
> accessible coverage for every fan, in any language.

## Use case

Streaming platforms and broadcasters send **one commentary and one graphics package to millions of very
different viewers**. Stats on screen say *what* happened, not *why it matters*; fans of a single player
lose them off the ball; fans outside the main market depend on whatever commentary exists in their language;
blind and low-vision fans get radio at best.

Pulse sits between the live event feed and each viewer's screen. A broadcaster plugs it in and gets:

- a **timed, machine-readable overlay feed** ready for the graphics engine (player tags, speed, pass difficulty,
  momentum, key-moment cards);
- **personalized narration** per viewer (analyst, casual, player focus, single-metric focus, accessibility),
  in any language, with voice;
- an **automated recap** for studio and on-demand.

All of it is generated from the same verified numbers: agents explain, they never invent statistics.

Pipeline: **Ingest → Interpret → Explain → Render → Personalize**

- **Chaos Index / Match Seismograph** — a live control-vs-chaos signal that flags instability before key moments.
- **Decision Value Added** — counterfactual xT: the value of the option chosen vs. the best one available.
- **Every Fan** — the same intelligence rendered for analysts, casual fans, kids, single-player focus,
  and fans who can't see or hear the match (spatial audio, sonification, multilingual audio description).

## Synthetic match generator

```bash
python3 -m generator.simulate --home NBR --away HRV --seed 7 --out data   # writes meta.json + events.jsonl
python3 -m generator.replay data/NBR-HRV-7.events.jsonl --speed 20        # live feed paced on timestamps
uv run --with pytest pytest -q
```

Clubs: `NBR` Northbridge Athletic, `HRV` Harbourside Rovers, `KMT` Kingsmoor Town,
`ASV` Ashvale United, `CLW` Calder Wharf FC, `SWC` Saltwick City — each with its own tactical DNA
(possession, pressing, verticality, width, tempo) and a stable roster.

Calibrated over 40 seeds: ~2.9 goals, ~27 shots (mean distance ~17.6 m), ~78% pass accuracy,
~97 minutes of play and ~105 km run per team.

Event schema: see [generator/schema.py](generator/schema.py). Coordinates are in the acting
team's frame, attacking toward x=105.

## Match intelligence engine

```bash
uv run python -m engine.fit --matches 120          # fit xG, pass-success, xT and Chaos reference on synthetic matches
uv run uvicorn engine.server:app --reload          # live server
# WS /ws/matches/NBR-HRV-7?speed=20&start_minute=75 -> event / overlay / moment / state messages
uv run --with pytest pytest -q
```

Every model is **trained on our own synthetic corpus** (120 matches, ~450k events):

| Model | What it gives the broadcast |
|---|---|
| xG (logistic: distance, angle, header) | chance quality on every shot |
| Pass success (logistic regression, 9 features) | **pass difficulty rating 0–100** |
| xT grid (value iteration, 16×12) | threat added by every pass |
| **Decision Value Added** | expected value of the chosen pass vs the best option in the 360-style freeze frame ("sliding doors") |
| **Chaos Index** | live control-vs-chaos percentile from turnovers, completion, pressing, ball swing, balance and shots, with the top drivers for explanation |

Key moments (goal with build-up and pre-goal tremor, big chance, brave pass, missed option, tremor,
control shift, milestones, recap) carry only computed facts, the input for the narrative agents.
Overlays are emitted as timed, machine-readable items: `{overlay_id, layer, template, in_ts, out_ts, priority, data}`.

## The newsroom: a multi-agent workflow (Microsoft Agent Framework + Microsoft Foundry)

Each key moment from the engine goes through a workflow of specialized agents:

```
Analyst ──► Tactician ──► Storyteller ──► Verifier ──► Localizer ──► Producer ──► timed cue
   │ evidence via MCP          ▲              │ numbers or players not in the evidence:
   │ (pulse-match-intel)       └──────────────┘ rewrite with feedback (max 2), then air the facts
   └─ "skip" ─► not aired
```

| Agent | Role |
|---|---|
| **Analyst** | Decides airtime (skip / brief / feature) and gathers evidence through the Pulse **MCP server** (player numbers, Chaos trend, team state) |
| **Tactician** | Explains *why* it matters: control vs chaos, pressure, rhythm, decision quality |
| **Storyteller** | Writes the same moment for each persona: casual, analyst, accessibility (written to be spoken), player focus |
| **Verifier** | Deterministic grounding: every number and player must trace back to the moment or the evidence ledger; rejects with feedback, never airs unverified text |
| **Localizer** | Translates for each market; translations must keep exactly the same numbers |
| **Producer** | Schedules the on-screen card (layer, in/out time, priority) so graphics never collide |

Reliability: schema-validated outputs, per-call timeouts, deterministic fallback per agent, stale moments
dropped when the newsroom lags behind live play, and a story cache so replays cost nothing.

```bash
# keyless auth to Microsoft Foundry (az login locally, managed identity in Azure)
export FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
export FOUNDRY_MODEL=gpt-4.1-mini
uv run uvicorn engine.server:app
# WS /ws/matches/NBR-HRV-7?speed=4&start_minute=77&langs=en,it,es&focus_player=HRV-11
# MCP  http://localhost:8000/mcp/  (list_sessions, get_match_state, get_player, get_chaos_trend, ...)
```

Without `FOUNDRY_PROJECT_ENDPOINT` (or with `PULSE_OFFLINE=1`) every agent uses its deterministic
fallback, which is also what the test-suite runs.
