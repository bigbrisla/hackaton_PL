"""MatchEngine: ingest live events, interpret them into stats, explainable metrics, key moments
and a timed overlay feed.

`ingest(event)` returns a list of messages, each a dict with a `kind`:

    event    the raw event plus `enriched` metrics (pass difficulty, xT added, DVA, xG...)
    overlay  deterministic broadcast graphic: {overlay_id, layer, template, in_ts, out_ts, priority, data}
    moment   a key moment with the facts and context the narrative agents may use
    state    periodic snapshot: score, clock, Chaos Index, team and player stats
"""

from __future__ import annotations

import itertools
from collections import defaultdict, deque

from .chaos import ChaosMeter
from .models import flip, option_value, pass_difficulty, pass_features, pass_success, xg, xt

SNAPSHOT_EVERY_S = 10.0
SPEED_TAG_KMH = 34.5
SHOT_SPEED_TAG_KMH = 105.0
DISTANCE_MILESTONES_M = (5_000, 10_000)
PASS_MILESTONES = (50, 75, 100)
TREMOR_CHAOS = 88
COOLDOWN_S = {"tremor": 360, "control_shift": 480, "pressing_surge": 600, "missed_option": 240, "brave_pass": 180}


def player_stats() -> dict:
    return dict(touches=0, passes=0, passes_completed=0, pass_distance=0.0, difficulty_completed=0,
                xt_added=0.0, dva=0.0, decisions=0, best_decisions=0, shots=0, xg=0.0, goals=0, assists=0,
                pressures=0, tackles_won=0, interceptions=0, distance_m=0, top_speed_kmh=0.0, sprints=0,
                max_shot_speed_kmh=0.0)


def team_stats() -> dict:
    return dict(goals=0, shots=0, shots_on_target=0, xg=0.0, passes=0, passes_completed=0, possession_s=0.0,
                pressures=0, tackles_won=0, interceptions=0, fouls=0, cards=0, corners=0, xt=0.0)


class MatchEngine:
    def __init__(self, meta: dict):
        self.meta = meta
        self.home_id, self.away_id = meta["home"]["id"], meta["away"]["id"]
        self.players = {p["id"]: {**p, "team_id": t["id"]} for t in (meta["home"], meta["away"]) for p in t["players"]}
        self.team_names = {t["id"]: t["name"] for t in (meta["home"], meta["away"])}
        self.score = {self.home_id: 0, self.away_id: 0}
        self.pstats = defaultdict(player_stats)
        self.tstats = {self.home_id: team_stats(), self.away_id: team_stats()}
        self.chaos = ChaosMeter(self.home_id)
        self.chaos_history: deque[tuple[float, dict]] = deque(maxlen=60)
        self.chaos_series: list[tuple[float, int]] = []  # whole match, for the seismograph
        self.recent: deque[dict] = deque(maxlen=40)
        self.last_ev: dict | None = None
        self.next_snapshot = 0.0
        self.last_moment_ts: dict[str, float] = {}
        self.last_control_side: str | None = None
        self.spell = (None, 0)  # (possession_id, consecutive completed passes)
        self.ids = itertools.count()
        self.moments: list[dict] = []
        self.minute, self.added = 0, 0
        self.where: dict | None = None  # location of the event being ingested

    # ------------------------------------------------------------------ helpers
    def name(self, pid: str | None) -> str | None:
        return self.players[pid]["name"] if pid in self.players else None

    def opponent(self, team_id: str) -> str:
        return self.away_id if team_id == self.home_id else self.home_id

    def home_xy(self, team_id: str | None, x: float | None, y: float | None) -> tuple | None:
        if x is None or team_id is None:
            return None
        return (round(x, 1), round(y, 1)) if team_id == self.home_id else tuple(round(v, 1) for v in flip(x, y))

    def clock(self, ev: dict) -> str:
        return f"{ev['minute']}'" + (f"+{ev['added_minute']}" if ev["added_minute"] else "")

    def cooled(self, key: str, ts: float, cooldown: float) -> bool:
        if ts - self.last_moment_ts.get(key, -1e9) < cooldown:
            return False
        self.last_moment_ts[key] = ts
        return True

    def overlay(self, ev: dict, layer: str, template: str, data: dict, duration: float = 5.0,
                priority: int = 50) -> dict:
        return {"kind": "overlay", "overlay_id": f"ov-{next(self.ids)}", "layer": layer, "template": template,
                "in_ts": ev["ts"], "out_ts": round(ev["ts"] + duration, 2), "priority": priority,
                "source_event": ev["id"], "data": data}

    def moment(self, ev: dict, type_: str, priority: int, title: str, facts: dict,
               team_id: str | None = None, player_id: str | None = None) -> dict:
        m = {"kind": "moment", "moment_id": f"m-{next(self.ids)}", "type": type_, "priority": priority,
             "ts": ev["ts"], "clock": self.clock(ev), "period": ev["period"], "source_event": ev["id"],
             "team_id": team_id, "team": self.team_names.get(team_id), "player_id": player_id,
             "player": self.name(player_id), "title": title, "facts": facts, "where": self.where,
             "context": {"score": dict(self.score), "chaos": self.chaos_now()}}
        self.moments.append(m)
        return m

    def chaos_now(self) -> dict | None:
        return self.chaos_history[-1][1] if self.chaos_history else None

    # ------------------------------------------------------------------ ingest
    def ingest(self, ev: dict) -> list[dict]:
        out: list[dict] = []
        self._possession_time(ev)
        self.chaos.add(ev)
        self.minute, self.added = ev["minute"], ev["added_minute"]
        enriched = self._enrich(ev)
        # a goal has no location of its own: keep the shot's
        self.where = self._where(ev, enriched) or (self.where if ev["type"] == "goal" else None)
        out.append({"kind": "event", "event": ev, "enriched": enriched})
        out += self._update_stats(ev, enriched)
        out += self._detect(ev, enriched)
        if ev["ts"] >= self.next_snapshot or ev["type"] in ("goal", "period_end", "match_end"):
            reading = self.chaos.reading()
            if reading:
                self.chaos_history.append((ev["ts"], reading))
                self.chaos_series.append((ev["ts"], reading["chaos"]))
                out += self._chaos_moments(ev, reading)
            out.append(self.snapshot(ev))
            self.next_snapshot = ev["ts"] + SNAPSHOT_EVERY_S
        self.recent.append({**ev, "enriched": enriched})
        self.last_ev = ev
        return out

    def _where(self, ev: dict, en: dict) -> dict | None:
        """Pitch location in words (acting team's view) plus home-frame coordinates for rendering and audio."""
        if ev["x"] is None:
            return None
        x, y = ev["x"], ev["y"]
        depth = ("inside the box" if x > 88.5 and abs(y - 34) < 20.16 else "in the final third" if x > 70
                 else "in midfield" if x > 35 else "deep in their own half")
        side = "on the right" if y < 22 else "on the left" if y > 46 else "centrally"
        return {"zone": f"{depth}, {side}", "home_xy": en["home_xy"]}

    def _possession_time(self, ev: dict) -> None:
        last = self.last_ev
        if last and last["type"] not in ("ball_out", "goal", "foul", "period_end") and ev["type"] != "set_piece":
            team = last["possession_team_id"]
            if team in self.tstats:
                self.tstats[team]["possession_s"] += max(0.0, ev["ts"] - last["ts"])

    def _enrich(self, ev: dict) -> dict:
        e: dict = {"home_xy": self.home_xy(ev["team_id"], ev["x"], ev["y"]),
                   "home_end_xy": self.home_xy(ev["team_id"], ev["end_x"], ev["end_y"])}
        if ev["type"] == "pass":
            a = ev["attrs"]
            tx, ty = ev["end_x"], ev["end_y"]
            if ev["outcome"] != "complete":
                for o in a.get("options", []):
                    if o["player_id"] == a.get("intended_receiver_id"):
                        tx, ty = o["x"], o["y"]
            feats = pass_features(ev["x"], ev["y"], tx, ty, ev["under_pressure"], a["height"])
            e["difficulty"] = pass_difficulty(feats)
            e["success_prob"] = round(pass_success(feats), 3)
            if ev["outcome"] == "complete":
                e["xt_added"] = round(xt(ev["end_x"], ev["end_y"]) - xt(ev["x"], ev["y"]), 4)
            else:
                e["xt_added"] = round(-xt(*flip(ev["end_x"], ev["end_y"])), 4)
            options = a.get("options", [])
            if len(options) > 1:
                chosen_ev, _ = option_value(ev["x"], ev["y"], tx, ty, ev["under_pressure"])
                best, best_ev, best_p = None, -1e9, 0.0
                for o in options:
                    v, p = option_value(ev["x"], ev["y"], o["x"], o["y"], ev["under_pressure"])
                    if v > best_ev:
                        best, best_ev, best_p = o, v, p
                e["dva"] = round(min(0.0, chosen_ev - best_ev), 4)
                e["best_option"] = {"player_id": best["player_id"], "player": self.name(best["player_id"]),
                                    "home_xy": self.home_xy(ev["team_id"], best["x"], best["y"]),
                                    "expected_value": round(best_ev, 4), "success_prob": round(best_p, 3)}
                e["chosen_value"] = round(chosen_ev, 4)
                e["options_home_xy"] = [{"player_id": o["player_id"],
                                         "home_xy": self.home_xy(ev["team_id"], o["x"], o["y"])} for o in options]
        elif ev["type"] == "shot":
            e["xg"] = round(xg(ev["x"], ev["y"], ev["attrs"].get("body_part", "foot")), 3)
        return e

    def _update_stats(self, ev: dict, en: dict) -> list[dict]:
        out = []
        t, pid, a = ev["team_id"], ev["player_id"], ev["attrs"]
        ts = self.tstats.get(t)
        ps = self.pstats[pid] if pid else None
        typ = ev["type"]
        if ps is not None and typ in ("pass", "carry", "shot"):
            ps["touches"] += 1
        speeds = [a.get("speed_kmh")] if typ in ("carry", "pressure") else []
        if typ == "pass" and a.get("receiver_run_kmh"):
            speeds.append(a["receiver_run_kmh"])
            runner = a.get("receiver_id") or a.get("intended_receiver_id")
        else:
            runner = pid
        for spd in filter(None, speeds):
            rp = self.pstats[runner]
            if spd > rp["top_speed_kmh"]:
                rp["top_speed_kmh"] = spd
            if spd >= SPEED_TAG_KMH:
                rp["sprints"] += 1
                out.append(self.overlay(ev, "player_badge", "speed_tag", {
                    "player_id": runner, "player": self.name(runner), "team_id": t, "speed_kmh": spd,
                    "match_top_speed_kmh": rp["top_speed_kmh"]}, 4.0, 40))

        if typ == "pass":
            ts["passes"] += 1
            ps["passes"] += 1
            ts["xt"] += max(0.0, en["xt_added"])
            ps["xt_added"] += max(0.0, en["xt_added"])  # threat created; losses are reflected in DVA
            if "dva" in en:
                ps["decisions"] += 1
                ps["dva"] += en["dva"]
                ps["best_decisions"] += en["dva"] > -0.002
            if ev["outcome"] == "complete":
                ts["passes_completed"] += 1
                ps["passes_completed"] += 1
                ps["pass_distance"] += a["length"]
                ps["difficulty_completed"] += en["difficulty"]
                n = ps["passes_completed"]
                if n in PASS_MILESTONES:
                    out.append(self.moment(ev, "milestone", 20, f"{self.name(pid)} completes pass number {n}",
                                           {"completed_passes": n, "pass_accuracy": round(n / ps["passes"], 3)}, t, pid))
                if en["difficulty"] >= 45:
                    out.append(self.overlay(ev, "lower_right", "pass_quality", {
                        "player_id": pid, "player": self.name(pid), "receiver": self.name(a["receiver_id"]),
                        "length_m": a["length"], "difficulty": en["difficulty"], "ball_speed_kmh": a["speed_kmh"],
                        "xt_added": en["xt_added"]}, 5.0, 45))
        elif typ == "shot":
            ts["shots"] += 1
            ts["xg"] += en["xg"]
            ps["shots"] += 1
            ps["xg"] += en["xg"]
            ts["shots_on_target"] += ev["outcome"] in ("goal", "saved")
            ps["max_shot_speed_kmh"] = max(ps["max_shot_speed_kmh"], a["speed_kmh"])
            out.append(self.overlay(ev, "lower_right", "shot_card", {
                "player_id": pid, "player": self.name(pid), "team_id": t, "shot_speed_kmh": a["speed_kmh"],
                "distance_m": a["distance"], "xg": en["xg"], "outcome": ev["outcome"]}, 6.0,
                70 if a["speed_kmh"] >= SHOT_SPEED_TAG_KMH else 55))
        elif typ == "goal":
            self.score[t] += 1
            ts["goals"] += 1
            ps["goals"] += 1
            if a.get("assist_id"):
                self.pstats[a["assist_id"]]["assists"] += 1
            out.append(self.overlay(ev, "scorebug", "goal_flash", {
                "team_id": t, "scorer": self.name(pid), "assist": self.name(a.get("assist_id")),
                "score": dict(self.score), "clock": self.clock(ev)}, 8.0, 100))
        elif typ == "pressure":
            ts["pressures"] += 1
            ps["pressures"] += 1
        elif typ == "tackle":
            ts["tackles_won"] += 1
            ps["tackles_won"] += 1
        elif typ == "interception":
            ts["interceptions"] += 1
            ps["interceptions"] += 1
        elif typ == "foul":
            ts["fouls"] += 1
        elif typ == "card":
            ts["cards"] += 1
        elif typ == "set_piece" and a.get("kind") == "corner":
            ts["corners"] += 1
        elif typ == "physical_update":
            before = ps["distance_m"]
            ps["distance_m"] = a["distance_m"]
            ps["top_speed_kmh"] = max(ps["top_speed_kmh"], a["top_speed_kmh"])
            for mark in DISTANCE_MILESTONES_M:
                if before < mark <= a["distance_m"]:
                    out.append(self.overlay(ev, "player_badge", "distance_tag", {
                        "player_id": pid, "player": self.name(pid), "team_id": t, "distance_km": round(mark / 1000, 1)},
                        4.0, 30))
                    if mark == DISTANCE_MILESTONES_M[-1]:
                        out.append(self.moment(ev, "milestone", 25, f"{self.name(pid)} passes {mark // 1000} km",
                                               {"distance_m": a["distance_m"], "top_speed_kmh": a["top_speed_kmh"],
                                                "sprints": a["sprints"]}, t, pid))
        return out

    # ------------------------------------------------------------------ key moments
    def _detect(self, ev: dict, en: dict) -> list[dict]:
        out, typ, t, pid, a = [], ev["type"], ev["team_id"], ev["player_id"], ev["attrs"]
        if typ == "goal":
            out.append(self._goal_moment(ev))
        elif typ == "shot" and ev["outcome"] != "goal" and en["xg"] >= 0.25:
            out.append(self.moment(ev, "big_chance", 70, f"Big chance for {self.name(pid)}",
                                   {"xg": en["xg"], "outcome": ev["outcome"], "shot_speed_kmh": a["speed_kmh"],
                                    "distance_m": a["distance"]}, t, pid))
        elif typ == "save" and a.get("shot_speed_kmh", 0) >= SHOT_SPEED_TAG_KMH:
            out.append(self.moment(ev, "big_save", 55, f"{self.name(pid)} stops a {a['shot_speed_kmh']:.0f} km/h shot",
                                   {"shot_speed_kmh": a["shot_speed_kmh"]}, t, pid))
        elif typ == "card":
            out.append(self.moment(ev, "card", 50, f"{a['card'].replace('_', ' ').title()} card for {self.name(pid)}",
                                   {"card": a["card"]}, t, pid))
        elif typ == "set_piece" and a.get("kind") == "penalty":
            out.append(self.moment(ev, "penalty", 85, f"Penalty to {self.team_names[t]}", {}, t, pid))
        elif typ == "pass" and "dva" in en:
            out += self._decision_moments(ev, en)
        elif typ in ("period_end", "match_end"):
            label = "Half time" if typ == "period_end" and ev["period"] == 1 else "Full time"
            if typ == "period_end" and ev["period"] == 2:
                return out  # full time is reported once, on match_end
            out.append(self.moment(ev, "recap", 90, label, self.summary()))

        if typ == "pass":
            pos_id, n = self.spell
            if ev["outcome"] == "complete":
                n = n + 1 if pos_id == ev["possession_id"] else 1
                self.spell = (ev["possession_id"], n)
                if n == 15:
                    out.append(self.moment(ev, "possession_spell", 40,
                                           f"{self.team_names[t]} string 15 passes together",
                                           {"consecutive_passes": n}, t, pid))
            else:
                self.spell = (None, 0)
        return out

    def _decision_moments(self, ev: dict, en: dict) -> list[dict]:
        out, t, pid = [], ev["team_id"], ev["player_id"]
        best = en["best_option"]
        brave = (ev["outcome"] == "complete" and en["dva"] > -0.002 and en["success_prob"] < 0.62
                 and en["xt_added"] >= 0.02)
        if brave and self.cooled(f"brave_pass:{t}", ev["ts"], COOLDOWN_S["brave_pass"]):
            out.append(self.moment(ev, "brave_pass", 55, f"{self.name(pid)} picks the boldest option",
                                   {"difficulty": en["difficulty"], "success_prob": en["success_prob"],
                                    "xt_added": en["xt_added"], "receiver": self.name(ev["attrs"]["receiver_id"]),
                                    "length_m": ev["attrs"]["length"]}, t, pid))
        elif (en["dva"] <= -0.03 and best["expected_value"] >= 0.03
              and self.cooled(f"missed_option:{t}", ev["ts"], COOLDOWN_S["missed_option"])):
            out.append(self.moment(ev, "missed_option", 45, f"Sliding doors: {best['player']} was the better option",
                                   {"dva": en["dva"], "chosen_value": en["chosen_value"],
                                    "best_option_value": best["expected_value"],
                                    "best_option_success_prob": best["success_prob"],
                                    "best_option_player": best["player"], "best_option_home_xy": best["home_xy"],
                                    "outcome": ev["outcome"]}, t, pid))
        return out

    def _goal_moment(self, ev: dict) -> dict:
        t, pid, a = ev["team_id"], ev["player_id"], ev["attrs"]
        chain = [e for e in self.recent if e["possession_id"] == ev["possession_id"] and e["team_id"] == t]
        passes = [e for e in chain if e["type"] == "pass" and e["outcome"] == "complete"]
        shot = next((e for e in reversed(self.recent) if e["type"] == "shot"), None)
        assist = passes[-1] if passes and passes[-1]["attrs"].get("receiver_id") == pid else None
        own, other = self.score[t], self.score[self.opponent(t)]
        effect = ("opener" if own + other == 1 else "equaliser" if own == other
                  else "takes_the_lead" if own == other + 1 else "extends_lead" if own > other else "pulls_one_back")
        facts = {
            "goal_effect": effect,
            "score_after": f"{self.team_names[self.home_id]} {self.score[self.home_id]}-"
                           f"{self.score[self.away_id]} {self.team_names[self.away_id]}",
            "build_up_passes": len(passes),
            "build_up_seconds": round(ev["ts"] - chain[0]["ts"], 1) if chain else 0,
            "build_up_xt": round(sum(max(0, p["enriched"].get("xt_added", 0)) for p in passes), 3),
            "assist": self.name(a.get("assist_id")),
        }
        if shot:
            facts.update(xg=shot["enriched"]["xg"], shot_speed_kmh=shot["attrs"]["speed_kmh"],
                         shot_distance_m=shot["attrs"]["distance"], body_part=shot["attrs"]["body_part"])
        if assist:
            facts.update(assist_difficulty=assist["enriched"]["difficulty"], assist_dva=assist["enriched"].get("dva"))
        window = [(ts, r) for ts, r in self.chaos_history if ev["ts"] - 240 <= ts < ev["ts"] - 20]
        if window:
            peak_ts, peak = max(window, key=lambda x: x[1]["chaos"])
            facts["chaos_peak_before"] = peak["chaos"]
            facts["chaos_peak_seconds_before"] = round(ev["ts"] - peak_ts)
            facts["tremor_before_goal"] = peak["chaos"] >= TREMOR_CHAOS - 5
        return self.moment(ev, "goal", 100, f"GOAL {self.team_names[t]}: {self.name(pid)}", facts, t, pid)

    def _chaos_moments(self, ev: dict, r: dict) -> list[dict]:
        out = []
        side_team = self.home_id if r["control_side"] == "home" else self.away_id
        if r["chaos"] >= TREMOR_CHAOS and self.cooled("tremor", ev["ts"], COOLDOWN_S["tremor"]):
            out.append(self.moment(ev, "tremor", 60, "Tremor: the match is breaking open",
                                   {"chaos": r["chaos"], "drivers": r["drivers"]}))
        if r["chaos"] <= 25 and r["control_share"] >= 0.62:
            if side_team != self.last_control_side and self.cooled("control_shift", ev["ts"], COOLDOWN_S["control_shift"]):
                self.last_control_side = side_team
                out.append(self.moment(ev, "control_shift", 55, f"{self.team_names[side_team]} take control",
                                       {"chaos": r["chaos"], "pass_share": r["control_share"], "drivers": r["drivers"]},
                                       side_team))
        out.append(self.overlay(ev, "meter", "chaos_meter", {**r, "control_team_id": side_team}, SNAPSHOT_EVERY_S, 20))
        return out

    # ------------------------------------------------------------------ snapshots
    def team_summary(self, team_id: str) -> dict:
        s = self.tstats[team_id]
        total_poss = sum(t["possession_s"] for t in self.tstats.values()) or 1
        return {"team_id": team_id, "name": self.team_names[team_id], "goals": s["goals"], "shots": s["shots"],
                "shots_on_target": s["shots_on_target"], "xg": round(s["xg"], 2),
                "possession": round(s["possession_s"] / total_poss, 3), "passes": s["passes"],
                "pass_accuracy": round(s["passes_completed"] / max(1, s["passes"]), 3),
                "pressures": s["pressures"], "tackles_won": s["tackles_won"], "interceptions": s["interceptions"],
                "fouls": s["fouls"], "cards": s["cards"], "corners": s["corners"], "xt": round(s["xt"], 2)}

    def player_summary(self, pid: str) -> dict:
        s, p = self.pstats[pid], self.players[pid]
        return {"player_id": pid, "name": p["name"], "team_id": p["team_id"], "position": p["position"],
                "number": p["number"], "touches": s["touches"], "passes": s["passes"],
                "pass_accuracy": round(s["passes_completed"] / max(1, s["passes"]), 3),
                "avg_pass_difficulty": round(s["difficulty_completed"] / max(1, s["passes_completed"]), 1),
                "xt_added": round(s["xt_added"], 3), "dva": round(s["dva"], 3),
                "decision_quality": round(s["best_decisions"] / max(1, s["decisions"]), 3),
                "shots": s["shots"], "xg": round(s["xg"], 2), "goals": s["goals"], "assists": s["assists"],
                "pressures": s["pressures"], "tackles_won": s["tackles_won"], "interceptions": s["interceptions"],
                "distance_km": round(s["distance_m"] / 1000, 2), "top_speed_kmh": s["top_speed_kmh"],
                "sprints": s["sprints"], "max_shot_speed_kmh": s["max_shot_speed_kmh"]}

    def leaders(self, n: int = 3) -> dict:
        ps = [self.player_summary(pid) for pid in self.players]
        return {
            "xt_added": [p["name"] for p in sorted(ps, key=lambda p: -p["xt_added"])[:n]],
            "top_speed_kmh": [p["name"] for p in sorted(ps, key=lambda p: -p["top_speed_kmh"])[:n]],
            "distance_km": [p["name"] for p in sorted(ps, key=lambda p: -p["distance_km"])[:n]],
            # hidden heroes: high threat created without goals or assists
            "hidden_heroes": [p["name"] for p in sorted(ps, key=lambda p: -p["xt_added"])
                              if p["goals"] == 0 and p["assists"] == 0][:n],
        }

    def summary(self) -> dict:
        return {"score": dict(self.score), "home": self.team_summary(self.home_id),
                "away": self.team_summary(self.away_id), "leaders": self.leaders(),
                "key_moments": [{"clock": m["clock"], "type": m["type"], "title": m["title"]}
                                for m in self.moments if m["priority"] >= 55][-12:]}

    def snapshot(self, ev: dict) -> dict:
        return {"kind": "state", "ts": ev["ts"], "clock": self.clock(ev), "period": ev["period"],
                "score": dict(self.score), "chaos": self.chaos_now(),
                "home": self.team_summary(self.home_id), "away": self.team_summary(self.away_id)}
