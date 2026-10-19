"""Approximate 22-player frames for rendering, derived from the event feed.

Synthetic events carry exact locations only for the players involved, so the other twenty are placed
with the same positional model the generator uses: the team in possession spreads into its formation
and shifts with the ball, the defending team squeezes into a compact block, the nearest defender
steps out to press, and the ball carrier sits exactly on the event location.
All output coordinates are in the home frame (home attacks toward x=105).
"""

from __future__ import annotations

import math

from .models import PITCH_LENGTH, PITCH_WIDTH, flip

GOAL_Y = PITCH_WIDTH / 2


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class FrameBuilder:
    def __init__(self, meta: dict):
        self.home_id = meta["home"]["id"]
        self.teams = {t["id"]: t for t in (meta["home"], meta["away"])}
        self.width = {t["id"]: 0.85 + 0.3 * t["dna"]["width"] for t in (meta["home"], meta["away"])}
        self.ball: tuple[float, float] = (52.5, 34.0)  # home frame
        self.possession: str = self.home_id

    def _to_home(self, team_id: str, x: float, y: float) -> tuple[float, float]:
        return (x, y) if team_id == self.home_id else flip(x, y)

    def _team_frame(self, team_id: str, ts: float, attacking: bool) -> dict[str, tuple[float, float]]:
        bx, by = self.ball if team_id == self.home_id else flip(*self.ball)
        out = {}
        for i, p in enumerate(self.teams[team_id]["players"]):
            sway = (math.sin(ts / 6.0 + i * 1.7) * 1.4, math.cos(ts / 7.5 + i * 2.3) * 1.4)
            if p["role"] == "GK":
                x = _clamp(3 + bx * 0.12, 2, 18) if attacking else _clamp(2 + bx * 0.05, 1.5, 7)
                y = _clamp(GOAL_Y + (by - GOAL_Y) * 0.15, 28, 40)
            elif attacking:
                x = min(p["base_x"] + (bx - 52.5) * 0.55, 97) + sway[0]
                y = GOAL_Y + (p["base_y"] - GOAL_Y) * self.width[team_id] + (by - GOAL_Y) * 0.25 + sway[1]
            else:  # compact block between the ball and its own goal
                x = p["base_x"] * 0.62 + 6 + (bx - 52.5) * 0.42 + sway[0] * 0.6
                y = GOAL_Y + (p["base_y"] - GOAL_Y) * 0.72 + (by - GOAL_Y) * 0.38 + sway[1] * 0.6
            out[p["id"]] = self._to_home(team_id, _clamp(x, 1, 104), _clamp(y, 1, 67))
        return out

    def frame(self, ev: dict, enriched: dict) -> list[list] | None:
        if enriched.get("home_xy") is None:
            return None
        self.ball = tuple(enriched["home_xy"])
        self.possession = ev.get("possession_team_id") or self.possession
        pos = {}
        for team_id in self.teams:
            pos.update(self._team_frame(team_id, ev["ts"], team_id == self.possession))
        # the nearest defender steps out to press the ball
        defenders = [p["id"] for tid, t in self.teams.items() if tid != self.possession for p in t["players"]
                     if p["role"] != "GK"]
        nearest = min(defenders, key=lambda pid: math.dist(pos[pid], self.ball))
        nx, ny = pos[nearest]
        pos[nearest] = (nx + (self.ball[0] - nx) * 0.7, ny + (self.ball[1] - ny) * 0.7)
        if ev.get("player_id") in pos:
            pos[ev["player_id"]] = self.ball
        return [[pid, round(x, 1), round(y, 1)] for pid, (x, y) in pos.items()]
