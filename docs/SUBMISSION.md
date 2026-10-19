# Submission

## Elevator pitch

**Pulse — one match, a million broadcasts.** Broadcasters send one commentary and one graphics package
to millions of very different viewers. Pulse sits between the live event feed and each screen and
generates a broadcast for every fan: timed, machine-readable overlays for the graphics engine, and
narration personalised for casual fans, analysts, single-player and single-metric followers, and fans
who cannot see the match, in any language.

Under the hood, a match engine trained on our own synthetic corpus computes chance quality (xG),
pass difficulty, expected threat, **Decision Value Added** (the value of the pass chosen versus every
option the passer had) and a live **Chaos Index** (control versus chaos). Six specialised agents on
**Microsoft Foundry**, orchestrated with **Microsoft Agent Framework**, turn each key moment into a
verified story: an analyst gathers evidence through our **MCP server**, a tactician explains why it
matters, a storyteller writes per persona, a verifier traces every number and name back to the engine
and sends drafts back when they don't match, a localizer adapts it for each market and a producer
schedules it on screen. In the demo match the verifier caught 12 ungrounded drafts; none reached the screen.

## Microsoft technologies

- **Microsoft Foundry**: project and `gpt-5-mini` deployment powering all agents, keyless (Microsoft Entra ID).
- **Microsoft Agent Framework**: the newsroom workflow (typed executors, conditional rewrite loop,
  structured outputs, tool calling, MCP tools).
- **Model Context Protocol**: the engine is an MCP server (`/mcp`) the agents use, also open to any MCP
  client (e.g. GitHub Copilot) to query a live match.
- **Azure AI Speech**: neural narration in English, Italian, Spanish and Japanese for the eyes-free mode.
- **Azure Container Apps**: one container (web app, WebSocket feed, agents, MCP), managed identity, scale to zero.
- **GitHub Actions** and **GitHub Container Registry**: tests, web build and container image on every push.

## What makes it different

- Explainable, original metrics (Chaos Index, Decision Value Added) fitted on a synthetic dataset we generate
  (120 matches, ~450k events, 360-style freeze frames), not just stats restated by a model.
- Grounding enforced in code: the model cannot put a number or a player on screen that the engine did not produce.
- Accessibility as the extreme case of personalisation: the match as spatial sound, heartbeat and voice.

## Testing instructions

1. Open the app link. Pick **Northbridge Athletic v Harbourside Rovers**, set **from 80'** and **2×**, click **Kick off**.
2. Switch personas on the right (Casual, Analyst, Player focus, One metric, Eyes-free) and languages (EN, IT, ES, 日本語).
3. Eyes-free: click **Sound**, then **Close your eyes** (headphones recommended).
4. Direct scenes: `?autostart=1&from=84&speed=2&persona=analyst` (sliding doors), `?autostart=1&from=90&speed=20` (recap).
5. Other fixtures run fully live through the agents (about 20 s per story).

Everything is synthetic: no real Premier League data, clubs or players.
