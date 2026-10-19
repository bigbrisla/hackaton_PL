"""Agent-lite football match simulator producing synthetic, football-realistic events.

The model is a possession chain: the ball carrier is pressed (or not), then picks
pass / carry / shot from zone, team DNA and match state. A latent per-team
momentum random walk plus game-state effects (chasing a result, fatigue) create
spells of control and chaos for the intelligence layer to discover.

    python -m generator.simulate --seed 7 --home NBR --away HRV --out data/
"""

from __future__ import annotations

import argparse
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

from .schema import GOAL_MOUTH, GOAL_Y, PITCH_LENGTH, PITCH_WIDTH, Event, EventType, flip
from .teams import Player, Team, all_teams

PERIOD_LENGTH = 45 * 60
PHYSICAL_INTERVAL = 2 * 60
DISTANCE_PER_MIN = {"GK": 55, "CB": 95, "FB": 108, "DM": 112, "CM": 118, "AM": 110, "W": 106, "ST": 100}
VENUES = ["Northgate Park", "The Wharfside", "Kingsmoor Lane", "Ashvale Stadium", "Saltwick Arena"]
REFEREES = ["M. Haldane", "R. Okoro", "S. Whitfield", "J. Calloway", "A. Prentice"]


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def shot_xg(x: float, y: float) -> float:
    """Cheap location-only xG, used only to drive shot decisions and outcomes."""
    d = math.hypot(PITCH_LENGTH - x, GOAL_Y - y)
    half = GOAL_MOUTH / 2
    a = abs(math.atan2(half, max(d, 0.5)) * 2)
    return 1 / (1 + math.exp(0.16 * d - 1.2 * a))


class MatchSimulator:
    def __init__(self, home: Team, away: Team, seed: int):
        self.rng = random.Random(seed)
        self.seed = seed
        self.teams = [home, away]
        self.match_id = f"{home.id}-{away.id}-{seed}"
        self.events: list[Event] = []
        self.score = [0, 0]
        self.momentum = [0.0, 0.0]
        self.period = 1
        self.period_clock = 0.0
        self.ts = 0.0
        self.possession_id = 0
        self.team_idx = 0
        self.carrier: Player = home.players[-1]
        self.x, self.y = 52.5, 34.0
        self.cards: dict[str, int] = {}
        self.distance = {p.id: 0.0 for t in self.teams for p in t.players}
        self.sprints = {p.id: 0 for t in self.teams for p in t.players}
        self.top_speed = {p.id: 0.0 for t in self.teams for p in t.players}
        self.next_physical = PHYSICAL_INTERVAL
        self.stoppage = 0.0

    # ---------------------------------------------------------------- helpers
    def emit(self, type_: EventType, team_idx: int | None = None, player: Player | None = None,
             x: float | None = None, y: float | None = None, **kw) -> Event:
        over = self.period_clock - PERIOD_LENGTH
        base_min = 0 if self.period == 1 else 45
        if over > 0:
            minute, added = base_min + 45, int(over // 60) + 1
        else:
            minute, added = base_min + int(self.period_clock // 60) + 1, 0
        ev = Event(
            id=f"{self.match_id}-{len(self.events):05d}", match_id=self.match_id, seq=len(self.events),
            ts=self.ts, period=self.period, period_clock=self.period_clock, minute=minute, added_minute=added,
            type=type_, team_id=self.teams[team_idx].id if team_idx is not None else None,
            player_id=player.id if player else None, x=x, y=y,
            possession_id=self.possession_id, possession_team_id=self.teams[self.team_idx].id, **kw,
        )
        self.events.append(ev)
        return ev

    def advance(self, seconds: float) -> None:
        self.ts += seconds
        self.period_clock += seconds

    def other(self, idx: int) -> int:
        return 1 - idx

    def minute(self) -> float:
        return self.period_clock / 60 + (45 if self.period == 2 else 0)

    def dna(self, idx: int) -> dict[str, float]:
        """Effective tactical parameters after momentum, scoreline and fatigue."""
        d = self.teams[idx].dna
        m = self.momentum[idx]
        diff = self.score[idx] - self.score[self.other(idx)]
        chasing = 1.0 if diff < 0 and self.minute() > 60 else 0.0
        protecting = 1.0 if diff > 0 and self.minute() > 70 else 0.0
        return dict(
            possession=clamp(d.possession - 0.15 * chasing + 0.1 * protecting, 0, 1),
            pressing=clamp(d.pressing + 0.25 * m + 0.2 * chasing - 0.15 * protecting, 0, 1),
            verticality=clamp(d.verticality + 0.2 * m + 0.25 * chasing - 0.1 * protecting, 0, 1),
            width=d.width,
            tempo=clamp(d.tempo + 0.15 * m + 0.15 * chasing, 0, 1),
        )

    def fatigue(self) -> float:
        return max(0.0, self.minute() - 60) * 0.0012

    def position_of(self, idx: int, p: Player, ball_x: float, ball_y: float) -> tuple[float, float]:
        """Approximate location of a player (in his team's frame) given the ball (same frame)."""
        if p.role == "GK":
            return clamp(3 + ball_x * 0.12, 2, 18), clamp(GOAL_Y + (ball_y - GOAL_Y) * 0.15, 28, 40)
        width = 0.85 + 0.3 * self.teams[idx].dna.width
        x = min(p.base_x + (ball_x - 52.5) * 0.55, 97) + self.rng.gauss(0, 4)
        y = GOAL_Y + (p.base_y - GOAL_Y) * width + (ball_y - GOAL_Y) * 0.25 + self.rng.gauss(0, 4)
        return clamp(x, 1, 104), clamp(y, 1, 67)

    def nearest(self, idx: int, x: float, y: float, exclude_gk: bool = True) -> Player:
        """Nearest player of team `idx` to point (x, y) expressed in that team's frame."""
        best, best_d = None, 1e9
        for p in self.teams[idx].players:
            if exclude_gk and p.role == "GK":
                continue
            px, py = self.position_of(idx, p, x, y)
            d = math.hypot(px - x, py - y) + self.rng.uniform(0, 6)
            if d < best_d:
                best, best_d = p, d
        return best

    def take_possession(self, idx: int, player: Player, x: float, y: float) -> None:
        if idx != self.team_idx:
            self.possession_id += 1
            self.momentum[idx] += 0.03
        self.team_idx, self.carrier, self.x, self.y = idx, player, clamp(x, 0.5, 104.5), clamp(y, 0.5, 67.5)

    def record_run(self, p: Player, dist: float, speed_kmh: float) -> None:
        self.top_speed[p.id] = max(self.top_speed[p.id], speed_kmh)
        if speed_kmh > 25:
            self.sprints[p.id] += 1

    # ---------------------------------------------------------------- restarts
    def restart(self, idx: int, kind: str, x: float, y: float, delay: float) -> None:
        self.advance(delay)
        self.stoppage += delay * 0.12
        if kind == "goal_kick":
            taker = self.teams[idx].players[0]
            x, y = 6.0, GOAL_Y
        elif kind == "kick_off":
            taker = next(p for p in self.teams[idx].players if p.role == "ST")
            x, y = 52.5, GOAL_Y
        elif kind == "corner":
            taker = max((p for p in self.teams[idx].players if p.role in ("W", "AM", "CM", "FB")),
                        key=lambda p: p.passing + self.rng.uniform(0, 10))
            x, y = 104.5, 0.5 if y < GOAL_Y else 67.5
        else:
            taker = self.nearest(idx, x, y)
        self.possession_id += 1 if idx != self.team_idx else 0
        self.team_idx, self.carrier, self.x, self.y = idx, taker, x, y
        self.emit(EventType.SET_PIECE, idx, taker, x, y, attrs={"kind": kind})
        if kind == "corner":
            self.corner()

    def ball_out(self, last_idx: int, x: float, y: float) -> None:
        """Ball left the pitch at (x, y) in last_idx frame, last touched by last_idx."""
        self.emit(EventType.BALL_OUT, last_idx, None, clamp(x, 0, 105), clamp(y, 0, 68))
        opp = self.other(last_idx)
        ox, oy = flip(clamp(x, 0, 105), clamp(y, 0, 68))
        if x >= PITCH_LENGTH:
            self.restart(opp, "goal_kick", ox, oy, self.rng.uniform(14, 26))
        elif x <= 0:
            self.restart(opp, "corner", ox, oy, self.rng.uniform(18, 30))
        else:
            self.restart(opp, "throw_in", ox, clamp(oy, 0.5, 67.5), self.rng.uniform(7, 16))

    # ---------------------------------------------------------------- actions
    def step(self) -> None:
        t, d = self.team_idx, self.other(self.team_idx)
        att, dfn = self.dna(t), self.dna(d)
        p = self.carrier
        self.momentum[t] += -0.015 * self.momentum[t] + self.rng.gauss(0, 0.035)
        self.momentum[d] += -0.015 * self.momentum[d] + self.rng.gauss(0, 0.035)
        for i in (0, 1):
            self.momentum[i] = clamp(self.momentum[i], -1, 1)

        under_pressure = False
        p_press = clamp(0.15 + 0.4 * dfn["pressing"] * (1 - self.x / PITCH_LENGTH) + 0.1 * self.momentum[d], 0.05, 0.7)
        if self.x > 80:
            p_press += 0.25
        if p.role != "GK" and self.rng.random() < p_press:
            dx, dy = flip(self.x, self.y)
            presser = self.nearest(d, dx, dy)
            run = clamp(16 + presser.pace * 0.1 + 6 * dfn["pressing"] + self.rng.gauss(0, 3), 10, 35.5)
            self.record_run(presser, 0, run)
            self.emit(EventType.PRESSURE, d, presser, dx, dy,
                      attrs={"duration": round(self.rng.uniform(0.6, 2.5), 1), "speed_kmh": round(run, 1)})
            self.advance(self.rng.uniform(0.3, 1.0))
            under_pressure = True
            if self.rng.random() < 0.035:
                self.foul(d, presser, p)
                return
            regain = 0.06 + 0.12 * dfn["pressing"] + (presser.tackling - p.composure) * 0.002 + 0.12 * (self.x > 80)
            if self.rng.random() < regain:
                self.emit(EventType.TACKLE, d, presser, dx, dy, outcome="won", attrs={"opponent_id": p.id})
                self.take_possession(d, presser, dx, dy)
                self.advance(self.rng.uniform(0.5, 1.5))
                return

        xg = shot_xg(self.x, self.y)
        p_shot = 0.0
        if xg > 0.035:
            p_shot = clamp(xg * 0.7 * (1.15 - 0.4 * att["possession"]) * (0.7 + p.finishing / 200), 0, 0.5)
        elif self.x > 72 and abs(self.y - GOAL_Y) < 20:
            p_shot = 0.05 + 0.03 * (p.finishing > 80)
        if p.role == "GK":
            p_shot = 0.0
        r = self.rng.random()
        if r < p_shot:
            self.shot(p, under_pressure, xg)
        elif r < p_shot + (0.22 + 0.002 * (p.pace - 70) - 0.1 * under_pressure) * (p.role != "GK"):
            self.carry(p, under_pressure, att, dfn)
        else:
            self.pass_(p, under_pressure, att, dfn)

    def pass_(self, p: Player, under_pressure: bool, att: dict, dfn: dict, forced_target: tuple | None = None) -> None:
        t, d = self.team_idx, self.other(self.team_idx)
        cands, weights = [], []
        if forced_target:
            mate, (mx, my) = forced_target
            cands, weights = [(mate, mx, my)], [1.0]
        else:
            for mate in self.teams[t].players:
                if mate.id == p.id or (mate.role == "GK" and self.x > 40):
                    continue
                mx, my = self.position_of(t, mate, self.x, self.y)
                dist = math.hypot(mx - self.x, my - self.y)
                if dist < 5 or dist > 65:
                    continue
                dx = mx - self.x
                w = math.exp(att["verticality"] * dx / 12 - dist / (14 + 14 * (1 - att["possession"])))
                if dist < 20:
                    w *= 1 + att["possession"]
                if under_pressure and dx < 0:
                    w *= 1.6
                w *= 0.6 + p.vision / 150
                cands.append((mate, mx, my))
                weights.append(w)
        if not cands:
            self.carry(p, under_pressure, att, dfn)
            return
        mate, mx, my = self.rng.choices(cands, weights)[0]
        dist = math.hypot(mx - self.x, my - self.y)
        dx = mx - self.x
        cross = self.x > 75 and (self.y < 16 or self.y > 52) and mx > 88
        through = dx > 15 and mx > 70 and not cross
        in_box = mx > 88.5 and abs(my - GOAL_Y) < 20.16
        p_ok = (1.0 - 0.006 * max(0, dist - 12) - 0.13 * under_pressure - 0.42 * in_box - 0.1 * (mx > 75)
                - 0.05 * max(0, dx) / 20 - 0.12 * cross - 0.06 * through
                + (p.passing - 72) * 0.004 - self.fatigue() - 0.04 * dfn["pressing"] * (self.x > 60))
        p_ok = clamp(p_ok, 0.25, 0.985)
        height = "high" if cross or dist > 32 else ("low" if dist > 18 else "ground")
        speed = clamp(38 + dist * 1.1 + self.rng.gauss(0, 6) + (10 if height == "high" else 0), 25, 110)
        kind = "cross" if cross else "through_ball" if through else ("back" if dx < -3 else "forward" if dx > 3 else "square")
        attrs = {"receiver_id": mate.id, "length": round(dist, 1), "height": height, "speed_kmh": round(speed, 1),
                 "pass_type": kind,
                 # 360-style freeze frame: teammates that were available as passing options
                 "options": [{"player_id": m.id, "x": round(ox, 1), "y": round(oy, 1)} for m, ox, oy in cands]}
        if through:
            run = clamp(24 + mate.pace * 0.11 + self.rng.gauss(0, 2), 20, 36.5)
            self.record_run(mate, 0, run)
            attrs["receiver_run_kmh"] = round(run, 1)
        duration = dist / (speed / 3.6)
        decide = 0.6 + self.rng.expovariate(1 / (1.7 * (1.25 - att["tempo"])))
        self.advance(decide)

        if self.rng.random() < p_ok:
            self.emit(EventType.PASS, t, p, self.x, self.y, end_x=mx, end_y=my, outcome="complete",
                      under_pressure=under_pressure, attrs=attrs)
            self.advance(duration)
            self.take_possession(t, mate, mx, my)
            return

        frac = self.rng.uniform(0.55, 1.15)
        ex = self.x + (mx - self.x) * frac + self.rng.gauss(0, 4)
        ey = self.y + (my - self.y) * frac + self.rng.gauss(0, 5)
        attrs["receiver_id"] = None
        attrs["intended_receiver_id"] = mate.id
        out = ex >= PITCH_LENGTH or ex <= 0 or ey <= 0 or ey >= PITCH_WIDTH
        self.emit(EventType.PASS, t, p, self.x, self.y, end_x=clamp(ex, 0, 105), end_y=clamp(ey, 0, 68),
                  outcome="out" if out else "incomplete", under_pressure=under_pressure, attrs=attrs)
        self.advance(duration)
        if out:
            self.ball_out(t, ex, ey)
            return
        ix, iy = flip(ex, ey)
        interceptor = self.nearest(d, ix, iy, exclude_gk=ix > 18)
        self.emit(EventType.INTERCEPTION, d, interceptor, ix, iy, outcome="won")
        self.take_possession(d, interceptor, ix, iy)

    def carry(self, p: Player, under_pressure: bool, att: dict, dfn: dict) -> None:
        t, d = self.team_idx, self.other(self.team_idx)
        dist = self.rng.uniform(3, 10 + p.pace / 7)
        angle = self.rng.gauss(0, 0.6) * (1.3 - att["verticality"])
        ex = clamp(self.x + dist * math.cos(angle), 1, 104)
        ey = clamp(self.y + dist * math.sin(angle) + (GOAL_Y - self.y) * 0.08, 1, 67)
        speed = clamp(14 + p.pace * 0.13 + self.rng.gauss(0, 2.5) + (3 if dist > 15 else 0), 8, 35.5)
        self.advance(dist / (speed / 3.6))
        self.record_run(p, dist, speed)
        challenge = under_pressure or self.rng.random() < 0.12 + 0.1 * dfn["pressing"] + 0.4 * (ex > 85)
        if challenge:
            dx, dy = flip(ex, ey)
            defender = self.nearest(d, dx, dy)
            p_lose = clamp(0.32 + (defender.tackling - p.composure) * 0.006 - (p.pace - 70) * 0.003, 0.12, 0.6)
            if self.rng.random() < p_lose:
                self.emit(EventType.CARRY, t, p, self.x, self.y, end_x=ex, end_y=ey, outcome="dispossessed",
                          under_pressure=under_pressure, attrs={"distance": round(dist, 1), "speed_kmh": round(speed, 1)})
                if self.rng.random() < 0.13:
                    self.x, self.y = ex, ey
                    self.foul(d, defender, p)
                    return
                self.emit(EventType.TACKLE, d, defender, dx, dy, outcome="won", attrs={"opponent_id": p.id})
                self.take_possession(d, defender, dx, dy)
                return
            beat = defender.id
        else:
            beat = None
        attrs = {"distance": round(dist, 1), "speed_kmh": round(speed, 1)}
        if beat:
            attrs["beat_player_id"] = beat
        self.emit(EventType.CARRY, t, p, self.x, self.y, end_x=ex, end_y=ey, outcome="complete",
                  under_pressure=under_pressure, attrs=attrs)
        self.x, self.y = ex, ey

    def shot(self, p: Player, under_pressure: bool, xg: float, body_part: str | None = None) -> None:
        t, d = self.team_idx, self.other(self.team_idx)
        att = self.dna(t)
        body_part = body_part or ("head" if self.rng.random() < 0.12 and self.x > 94 else "foot")
        d_goal = math.hypot(PITCH_LENGTH - self.x, GOAL_Y - self.y)
        speed = clamp(72 + p.finishing * 0.25 - (18 if d_goal < 9 else 0) - (25 if body_part == "head" else 0)
                      + self.rng.gauss(0, 9), 35, 132)
        self.advance(0.8 + self.rng.random() * (1.3 - att["tempo"]))
        gk = self.teams[d].players[0]
        p_goal = xg * (0.33 + p.finishing / 600 + p.composure / 1000) * (1.2 - gk.composure / 400) * (0.8 if under_pressure else 1)
        if body_part == "head":
            p_goal *= 0.75
        r = self.rng.random()
        end_y = GOAL_Y + self.rng.gauss(0, 3.2)
        attrs = {"speed_kmh": round(speed, 1), "body_part": body_part, "distance": round(d_goal, 1)}
        if r < p_goal:
            self.emit(EventType.SHOT, t, p, self.x, self.y, end_x=PITCH_LENGTH, end_y=clamp(end_y, 30.5, 37.5),
                      outcome="goal", under_pressure=under_pressure, attrs=attrs)
            self.goal(t, p)
            return
        r = self.rng.random()
        if r < 0.33:
            self.emit(EventType.SHOT, t, p, self.x, self.y, end_x=PITCH_LENGTH, end_y=clamp(end_y, 30.5, 37.5),
                      outcome="saved", under_pressure=under_pressure, attrs=attrs)
            self.advance(0.4)
            gx, gy = flip(PITCH_LENGTH - 1, end_y)
            self.emit(EventType.SAVE, d, gk, gx, gy, attrs={"shot_speed_kmh": round(speed, 1)})
            if self.rng.random() < 0.35:
                self.restart(t, "corner", PITCH_LENGTH, 0 if self.rng.random() < 0.5 else PITCH_WIDTH, self.rng.uniform(18, 28))
            else:
                self.take_possession(d, gk, gx, gy)
                self.advance(self.rng.uniform(3, 8))
        elif r < 0.58:
            bx, by = self.x + (PITCH_LENGTH - self.x) * 0.25, self.y + (GOAL_Y - self.y) * 0.25
            self.emit(EventType.SHOT, t, p, self.x, self.y, end_x=bx, end_y=by, outcome="blocked",
                      under_pressure=under_pressure, attrs=attrs)
            if self.rng.random() < 0.4:
                self.restart(t, "corner", PITCH_LENGTH, self.y, self.rng.uniform(18, 28))
            else:
                ix, iy = flip(bx, by)
                blocker = self.nearest(d, ix, iy)
                self.take_possession(d, blocker, ix, iy)
        else:
            oy = GOAL_Y + self.rng.choice([-1, 1]) * self.rng.uniform(4.2, 12)
            self.emit(EventType.SHOT, t, p, self.x, self.y, end_x=PITCH_LENGTH, end_y=oy, outcome="off_target",
                      under_pressure=under_pressure, attrs=attrs)
            self.ball_out(t, PITCH_LENGTH + 1, oy)

    def corner(self) -> None:
        t = self.team_idx
        att, dfn = self.dna(t), self.dna(self.other(t))
        targets = [m for m in self.teams[t].players if m.role in ("CB", "ST", "DM", "CM", "AM")]
        mate = max(targets, key=lambda m: m.finishing + m.composure + self.rng.uniform(0, 40))
        tx, ty = self.rng.uniform(92, 101), self.rng.uniform(26, 42)
        before = len(self.events)
        self.pass_(self.carrier, False, att, dfn, forced_target=(mate, (tx, ty)))
        last = self.events[before] if len(self.events) > before else None
        if last and last.outcome == "complete" and self.rng.random() < 0.55:
            self.shot(mate, True, shot_xg(tx, ty) * 0.8, body_part="head")

    def foul(self, offender_idx: int, offender: Player, victim: Player) -> None:
        vx, vy = self.x, self.y
        ox, oy = flip(vx, vy)
        self.emit(EventType.FOUL, offender_idx, offender, ox, oy, attrs={"victim_id": victim.id})
        p_card = 0.1 + 0.1 * (vx > 70)
        if self.rng.random() < p_card:
            n = self.cards.get(offender.id, 0) + 1
            self.cards[offender.id] = n
            self.emit(EventType.CARD, offender_idx, offender, ox, oy, attrs={"card": "yellow" if n == 1 else "second_yellow"})
        victim_idx = self.other(offender_idx)
        if vx > 88.5 and abs(vy - GOAL_Y) < 20.16 and self.rng.random() < 0.12:
            self.advance(self.rng.uniform(40, 70))
            self.team_idx, self.carrier, self.x, self.y = victim_idx, victim, 94.0, GOAL_Y
            self.emit(EventType.SET_PIECE, victim_idx, victim, 94.0, GOAL_Y, attrs={"kind": "penalty"})
            self.shot(victim, False, 0.78)
            return
        self.restart(victim_idx, "free_kick", vx, vy, self.rng.uniform(15, 35))

    def goal(self, t: int, scorer: Player) -> None:
        self.score[t] += 1
        assist = None
        for ev in reversed(self.events[-6:-1]):
            if ev.type == EventType.PASS and ev.outcome == "complete" and ev.attrs.get("receiver_id") == scorer.id:
                assist = ev.player_id
                break
        self.emit(EventType.GOAL, t, scorer, attrs={"assist_id": assist, "score": {
            self.teams[0].id: self.score[0], self.teams[1].id: self.score[1]}})
        conceding = self.other(t)
        self.momentum[conceding] = clamp(self.momentum[conceding] + 0.3, -1, 1)
        self.momentum[t] = clamp(self.momentum[t] - 0.1, -1, 1)
        self.stoppage += 30
        self.restart(conceding, "kick_off", 52.5, GOAL_Y, self.rng.uniform(55, 85))

    # ---------------------------------------------------------------- physical
    def physical_update(self) -> None:
        mins = self.minute()
        for idx, team in enumerate(self.teams):
            press = team.dna.pressing
            for p in team.players:
                per_min = DISTANCE_PER_MIN[p.role] * (0.9 + p.stamina / 700) * (1 + 0.08 * press)
                self.distance[p.id] += per_min * PHYSICAL_INTERVAL / 60 * self.rng.uniform(0.92, 1.08) * (1 - self.fatigue() * 2)
                spd = 24 + p.pace * 0.085 + self.rng.gauss(0, 1.2) - (4 if p.role == "GK" else 0)
                self.top_speed[p.id] = max(self.top_speed[p.id], round(spd, 1))
                if self.rng.random() < 0.6 and p.role != "GK":
                    self.sprints[p.id] += self.rng.randint(1, 4)
                self.emit(EventType.PHYSICAL, idx, p, attrs={
                    "distance_m": round(self.distance[p.id]), "top_speed_kmh": round(self.top_speed[p.id], 1),
                    "sprints": self.sprints[p.id], "minutes": round(mins, 1)})

    # ---------------------------------------------------------------- loop
    def play_period(self, period: int, kick_off_idx: int) -> None:
        self.period, self.period_clock, self.stoppage = period, 0.0, 0.0
        self.next_physical = PHYSICAL_INTERVAL
        self.emit(EventType.PERIOD_START, attrs={"period": period})
        self.restart(kick_off_idx, "kick_off", 52.5, GOAL_Y, 0)
        while True:
            added = math.ceil(clamp(self.stoppage / 60 + 1 + self.rng.random() * 0.5, 1, 9))
            if self.period_clock >= PERIOD_LENGTH + added * 60:
                break
            self.step()
            if self.period_clock >= self.next_physical:
                self.physical_update()
                self.next_physical += PHYSICAL_INTERVAL
        self.emit(EventType.PERIOD_END, attrs={"period": period, "score": {
            self.teams[0].id: self.score[0], self.teams[1].id: self.score[1]}})

    def run(self) -> tuple[dict, list[Event]]:
        meta = self.meta()
        self.emit(EventType.MATCH_START, attrs={"home": self.teams[0].id, "away": self.teams[1].id})
        first = self.rng.randint(0, 1)
        self.play_period(1, first)
        self.play_period(2, 1 - first)
        self.emit(EventType.MATCH_END, attrs={"score": {self.teams[0].id: self.score[0], self.teams[1].id: self.score[1]}})
        meta["final_score"] = {self.teams[0].id: self.score[0], self.teams[1].id: self.score[1]}
        return meta, self.events

    def meta(self) -> dict:
        kickoff = datetime(2026, 8, 15, 15, 0) + timedelta(days=self.rng.randint(0, 270))
        return {
            "match_id": self.match_id, "seed": self.seed, "synthetic": True,
            "competition": "Synthetic Premier Showcase", "kickoff": kickoff.isoformat(),
            "venue": self.rng.choice(VENUES), "referee": self.rng.choice(REFEREES),
            "weather": self.rng.choice(["clear", "overcast", "light rain", "windy", "cold and dry"]),
            "attendance": self.rng.randint(28000, 61000),
            "pitch": {"length": PITCH_LENGTH, "width": PITCH_WIDTH},
            "coordinate_frame": "event team attacks toward x=105; y=0 is that team's right touchline",
            "home": self.teams[0].to_dict(), "away": self.teams[1].to_dict(),
        }


def simulate(home_id: str, away_id: str, seed: int) -> tuple[dict, list[Event]]:
    teams = {t.id: t for t in all_teams()}
    return MatchSimulator(teams[home_id], teams[away_id], seed).run()


def save(meta: dict, events: list[Event], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / f"{meta['match_id']}.meta.json"
    events_path = out_dir / f"{meta['match_id']}.events.jsonl"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    with events_path.open("w") as f:
        for ev in events:
            f.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")
    return meta_path, events_path


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", default="NBR")
    ap.add_argument("--away", default="HRV")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=Path, default=Path("data"))
    args = ap.parse_args()
    meta, events = simulate(args.home, args.away, args.seed)
    meta_path, events_path = save(meta, events, args.out)
    score = meta["final_score"]
    print(f"{meta['home']['name']} {score[args.home]} - {score[args.away]} {meta['away']['name']}"
          f"  ({len(events)} events) -> {events_path}")


if __name__ == "__main__":
    main()
