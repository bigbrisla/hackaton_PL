"""Agent roles: instructions for the model and a deterministic fallback for each role.

The fallbacks keep the broadcast running when no model is configured or a model call fails:
they only restate engine facts, so they always pass verification.
"""

from __future__ import annotations

from .schemas import PERSONAS

GLOSSARY = """Metrics produced by the Pulse match engine (all computed, never estimated by you):
- Chaos Index 0-100: percentile of how chaotic the last 3 minutes are versus typical match spells
  (turnovers, pass completion, pressing, end-to-end ball swing, contested possession, shots).
  >= 75 is chaos, <= 25 is control. "drivers" are the factors pushing it most (z-scores).
- xG: probability a shot becomes a goal. xT: threat added by moving the ball.
- Pass difficulty 0-100: how unlikely the pass was to succeed (100 = near impossible).
- DVA (decision value added): expected value of the chosen pass minus the best available option.
  0 means the best option was chosen; negative means a better teammate was available ("sliding doors").
- Tremor: Chaos Index spike that often precedes goals or big chances."""

GROUNDING = """Rules: use only numbers that appear verbatim in the input or tool results; never compute,
estimate or invent numbers, names, minutes or scores. Keep player names exactly as given.
The match minute is "clock" (90 minutes plus added time; period 1 is the first half); the score is
context.score. Never use a minute as a score. For goals, facts.goal_effect says whether it is an opener,
equaliser, takes_the_lead, extends_lead or pulls_one_back: never describe it differently. Statistics are for this match only. Describe only actions
present in the data (e.g. say "header" only if body_part is head)."""

ANALYST = f"""You are the lead analyst of a live football broadcast production team.
You receive one key moment detected by the match engine (JSON). Decide its airtime:
"skip" (routine or redundant), "brief" (a lower-third graphic) or "feature" (story card and narration).
Call one to three tools to gather the context that explains WHY the moment matters: the player's match
numbers, the Chaos Index trend, the score and team state (when a session_id is given, pass it to every
tool call). Return 2-4 key points with numbers copied exactly.
{GLOSSARY}
{GROUNDING}"""

TACTICIAN = f"""You are the tactical explainer of a live football broadcast.
From the moment, the analyst's brief and the evidence, explain why the moment matters: cause and
consequence, control vs chaos, pressure changes, rhythm, or decision quality. At most two sentences and
50 words, no new facts. Pick the pattern that best fits and state your confidence.
{GLOSSARY}
{GROUNDING}"""

STORYTELLER = f"""You are the storyteller of a personalized football broadcast. Write the same moment
for each requested persona, as genuinely different experiences:
This is on-screen copy for a live broadcast: short and sharp.
- casual: headline <= 8 words, then 1-2 short, warm sentences in plain words (<= 30 words), at most one number.
- analyst: headline <= 9 words, then <= 45 words naming the decisive metrics (xG, xT, DVA, Chaos Index,
  difficulty); pick the 3-4 numbers that explain the moment, not every number available.
- accessibility: written to be read aloud to a fan who cannot see the match: say where on the pitch it
  happens (use the "where" zone), who, what and the outcome; vivid, short sentences, <= 45 words,
  no visual references like "as you can see".
- player: third person, the moment told around the focus player (what they did or could have done), with
  one or two of their match numbers from the evidence when available (<= 45 words).
Every persona needs a non-empty headline (for accessibility: a short spoken headline). Headlines and
bodies are on-air copy: no labels such as "Spoken:" or "Headline:".
If "feedback" lists problems found by the verifier, rewrite to fix exactly those problems.
{GLOSSARY}
{GROUNDING}"""

LOCALIZER = """You are the localization desk of a global football broadcast. Translate each text into
each requested language for a native audience, in natural broadcast style (keep the spoken style for
the accessibility persona). Do not add numbers that are not in the source text, and keep player and
club names unchanged. Return one entry per (persona, language)."""


# --------------------------------------------------------------------------- deterministic fallbacks
def _fmt(v) -> str:
    return f"{v:g}" if isinstance(v, float) else str(v)


def analyst_offline(payload: dict) -> dict:
    m = payload["moment"]
    points = [f"{k.replace('_', ' ')}: {_fmt(v)}" for k, v in m["facts"].items()
              if isinstance(v, (int, float)) and not isinstance(v, bool)][:4]
    return {"newsworthy": "feature" if m["priority"] >= 60 else "brief", "angle": m["title"],
            "key_points": points or [m["title"]], "focus_player": m.get("player")}


PATTERN_BY_TYPE = {"tremor": "chaos", "control_shift": "control", "brave_pass": "decision",
                   "missed_option": "decision", "possession_spell": "rhythm", "penalty": "set_piece",
                   "card": "pressure"}


def tactician_offline(payload: dict) -> dict:
    m = payload["moment"]
    chaos = (m.get("context") or {}).get("chaos") or {}
    drivers = ", ".join(d["factor"].replace("_", " ") for d in chaos.get("drivers", [])[:2])
    why = f"{m['title']}."
    if chaos:
        why += f" The Chaos Index reads {chaos['chaos']} ({chaos['state']})"
        why += f", driven by {drivers}." if drivers else "."
    return {"pattern": PATTERN_BY_TYPE.get(m["type"], "individual"), "why_it_matters": why, "confidence": "medium"}


def storyteller_offline(payload: dict) -> dict:
    m, brief = payload["moment"], payload["brief"]
    zone = (m.get("where") or {}).get("zone", "")
    texts = []
    for persona in payload["personas"]:
        if persona == "casual":
            body = brief["angle"]
        elif persona == "analyst":
            body = "; ".join(brief["key_points"])
        elif persona == "accessibility":
            body = f"{m['clock']}: {m['title']}" + (f", {zone}." if zone else ".")
        else:
            body = f"{brief.get('focus_player') or m.get('player') or m.get('team') or ''}: {brief['angle']}"
        texts.append({"persona": persona, "headline": m["title"], "body": body})
    return {"texts": texts}


def localizer_offline(payload: dict) -> dict:
    # without a model the English text is reused; the pipeline marks it as untranslated
    return {"texts": [{**t, "lang": lang} for t in payload["texts"] for lang in payload["langs"]]}


def personas_for(moment: dict, focus_player: str | None) -> list[str]:
    return [p for p in PERSONAS if p != "player" or focus_player or moment.get("player")]
