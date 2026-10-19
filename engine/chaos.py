"""Chaos Index: a live 0-100 signal of how controlled or chaotic the match is right now.

Computed on a rolling window of on-ball events from six components, each z-scored against
reference values fitted on synthetic matches (engine/fit.py) so 50 means "a typical spell".

    turnovers      possession changes per minute           (more = chaos)
    completion     pass completion rate                    (less = chaos)
    pressures      pressing actions per minute             (more = chaos)
    ball_swing     mean end-to-end ball movement per event (more = chaos)
    balance        how evenly the ball is shared            (contested = chaos)
    shots          shots per minute                         (more = chaos)
"""

from __future__ import annotations

import math
from collections import deque

from .models import PITCH_LENGTH, flip, load_models

WINDOW_S = 180.0
ON_BALL = {"pass", "carry", "shot", "tackle", "interception", "pressure", "set_piece", "save"}
WEIGHTS = {"turnovers": 0.28, "completion": -0.2, "pressures": 0.14, "ball_swing": 0.16, "balance": 0.1, "shots": 0.12}


def home_frame_x(ev: dict, home_id: str) -> float | None:
    if ev.get("x") is None:
        return None
    return ev["x"] if ev["team_id"] == home_id else flip(ev["x"], ev["y"])[0]


class ChaosMeter:
    def __init__(self, home_id: str, window: float = WINDOW_S):
        self.home_id = home_id
        self.window = window
        self.events: deque[dict] = deque()

    def add(self, ev: dict) -> None:
        if ev["type"] in ON_BALL:
            self.events.append(ev)
        while self.events and ev["ts"] - self.events[0]["ts"] > self.window:
            self.events.popleft()

    def components(self) -> dict[str, float] | None:
        evs = list(self.events)
        if len(evs) < 25 or evs[-1]["ts"] - evs[0]["ts"] < 90:
            return None
        minutes = max(1.0, (evs[-1]["ts"] - evs[0]["ts"]) / 60)
        changes = sum(1 for a, b in zip(evs, evs[1:]) if a["possession_team_id"] != b["possession_team_id"])
        passes = [e for e in evs if e["type"] == "pass"]
        completed = [e for e in passes if e["outcome"] == "complete"]
        xs = [x for x in (home_frame_x(e, self.home_id) for e in evs) if x is not None]
        swing = sum(abs(b - a) for a, b in zip(xs, xs[1:])) / max(1, len(xs) - 1)
        home_share = sum(e["team_id"] == self.home_id for e in completed) / max(1, len(completed))
        return {
            "turnovers": changes / minutes,
            "completion": len(completed) / max(1, len(passes)),
            "pressures": sum(e["type"] == "pressure" for e in evs) / minutes,
            "ball_swing": swing / PITCH_LENGTH * 100,
            "balance": 1 - abs(home_share - 0.5) * 2,
            "shots": sum(e["type"] == "shot" for e in evs) / minutes,
            "home_share": home_share,
        }

    def reading(self) -> dict | None:
        comp = self.components()
        if comp is None:
            return None
        ref = load_models()["chaos_ref"]
        z = zscores(comp, ref)
        # percentile of the combined score among typical match spells (normal approximation)
        chaos = round(100 * 0.5 * (1 + math.erf(combined_score(comp, ref) / ref["score"][1] / math.sqrt(2))))
        share = comp["home_share"]
        return {
            "chaos": chaos,
            "state": "chaos" if chaos >= 75 else "control" if chaos <= 25 else "contested",
            "control_side": "home" if share >= 0.5 else "away",
            "control_share": round(max(share, 1 - share), 2),
            # the components pushing the index hardest, for the explainer agents
            "drivers": sorted(({"factor": k, "z": round(z[k] * (1 if WEIGHTS[k] > 0 else -1), 2),
                                "value": round(comp[k], 2)} for k in WEIGHTS),
                              key=lambda d: -abs(d["z"]))[:3],
        }


def zscores(comp: dict, ref: dict) -> dict[str, float]:
    return {k: (comp[k] - ref[k][0]) / (ref[k][1] or 1) for k in WEIGHTS}


def combined_score(comp: dict, ref: dict) -> float:
    z = zscores(comp, ref)
    return sum(WEIGHTS[k] * z[k] for k in WEIGHTS) / sum(abs(w) for w in WEIGHTS.values())


def reference_samples(events: list[dict], home_id: str, step: float = 30.0) -> list[dict]:
    """Sample raw components every `step` seconds; used to fit the reference distribution."""
    meter, out, next_ts = ChaosMeter(home_id), [], WINDOW_S
    for ev in events:
        meter.add(ev)
        if ev["ts"] >= next_ts:
            comp = meter.components()
            if comp:
                out.append(comp)
            next_ts += step
    return out


def mean_std(values: list[float]) -> tuple[float, float]:
    m = sum(values) / len(values)
    return m, math.sqrt(sum((v - m) ** 2 for v in values) / len(values))
