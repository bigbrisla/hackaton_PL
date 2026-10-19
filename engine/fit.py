"""Fit the engine's models on a corpus of synthetic matches.

    python -m engine.fit --matches 120

Writes engine/data/models.json with:
- pass_model: logistic regression weights (IRLS) for pass success -> difficulty rating
- xt_grid: expected threat by value iteration over possession chains
- chaos_ref: mean/std of each Chaos Index component
"""

from __future__ import annotations

import argparse
import itertools
import json

import numpy as np

from generator.simulate import simulate
from generator.teams import CLUBS

from .chaos import WEIGHTS, combined_score, mean_std, reference_samples
from .models import FEATURE_NAMES, MODEL_PATH, XT_COLS, XT_ROWS, pass_features, shot_features, xt_cell


def corpus(n: int) -> list[tuple[dict, list[dict]]]:
    pairs = list(itertools.permutations([c["id"] for c in CLUBS], 2))
    out = []
    for i in range(n):
        home, away = pairs[i % len(pairs)]
        meta, events = simulate(home, away, 10_000 + i)
        out.append((meta, [e.to_dict() for e in events]))
    return out


def pass_target(ev: dict) -> tuple[float, float]:
    """Where the passer aimed: the receiver for completed passes, the intended teammate otherwise."""
    if ev["outcome"] == "complete":
        return ev["end_x"], ev["end_y"]
    intended = ev["attrs"].get("intended_receiver_id")
    for opt in ev["attrs"].get("options", []):
        if opt["player_id"] == intended:
            return opt["x"], opt["y"]
    return ev["end_x"], ev["end_y"]


def logistic(X: np.ndarray, y: np.ndarray, ridge: float = 1e-3) -> np.ndarray:
    w = np.zeros(X.shape[1])
    for _ in range(25):  # IRLS / Newton steps with a small ridge
        p = 1 / (1 + np.exp(-X @ w))
        H = X.T @ (X * (p * (1 - p))[:, None]) + ridge * np.eye(len(w))
        w -= np.linalg.solve(H, X.T @ (p - y) + ridge * w)
    return w


def fit_xg_model(matches) -> dict:
    X, y = [], []
    for _, events in matches:
        for ev in events:
            if ev["type"] == "shot":
                X.append(shot_features(ev["x"], ev["y"], ev["attrs"]["body_part"]))
                y.append(1.0 if ev["outcome"] == "goal" else 0.0)
    X, y = np.array(X), np.array(y)
    w = logistic(X, y)
    return {"features": ["bias", "distance_10m", "goal_angle", "header"], "weights": [round(float(v), 4) for v in w],
            "samples": int(len(y)), "conversion": round(float(y.mean()), 4)}


def fit_pass_model(matches) -> dict:
    X, y = [], []
    for _, events in matches:
        for ev in events:
            if ev["type"] == "pass":
                tx, ty = pass_target(ev)
                X.append(pass_features(ev["x"], ev["y"], tx, ty, ev["under_pressure"], ev["attrs"]["height"]))
                y.append(1.0 if ev["outcome"] == "complete" else 0.0)
    X, y = np.array(X), np.array(y)
    w = logistic(X, y)
    p = 1 / (1 + np.exp(-X @ w))
    brier = float(np.mean((p - y) ** 2))
    return {"features": FEATURE_NAMES, "weights": [round(float(v), 4) for v in w],
            "samples": int(len(y)), "base_rate": round(float(y.mean()), 4), "brier": round(brier, 4)}


def fit_xt(matches, iterations: int = 40) -> list[list[float]]:
    n = XT_COLS * XT_ROWS
    shots, goals, moves, total = np.zeros(n), np.zeros(n), np.zeros(n), np.zeros(n)
    trans = np.zeros((n, n))

    def idx(x, y):
        c, r = xt_cell(x, y)
        return r * XT_COLS + c

    for _, events in matches:
        for ev in events:
            if ev["type"] not in ("pass", "carry", "shot") or ev["x"] is None:
                continue
            i = idx(ev["x"], ev["y"])
            total[i] += 1
            if ev["type"] == "shot":
                shots[i] += 1
                goals[i] += ev["outcome"] == "goal"
            else:
                moves[i] += 1
                if ev["outcome"] == "complete":
                    trans[i, idx(ev["end_x"], ev["end_y"])] += 1
    total = np.maximum(total, 1)
    p_shot, p_move = shots / total, moves / total
    p_goal = np.divide(goals, shots, out=np.zeros(n), where=shots > 0)
    T = trans / np.maximum(moves, 1)[:, None]
    v = np.zeros(n)
    for _ in range(iterations):
        v = p_shot * p_goal + p_move * (T @ v)
    return [[round(float(v[r * XT_COLS + c]), 4) for c in range(XT_COLS)] for r in range(XT_ROWS)]


def fit_chaos_ref(matches) -> dict:
    samples = [s for meta, events in matches for s in reference_samples(events, meta["home"]["id"])]
    ref = {k: [round(v, 4) for v in mean_std([s[k] for s in samples])] for k in WEIGHTS}
    # spread of the combined score, so the index reads as a percentile of typical match spells
    ref["score"] = [0.0, round(mean_std([combined_score(s, ref) for s in samples])[1], 4)]
    return ref


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matches", type=int, default=120)
    args = ap.parse_args()
    matches = corpus(args.matches)
    models = {
        "fitted_on": {"matches": args.matches, "events": sum(len(e) for _, e in matches)},
        "pass_model": fit_pass_model(matches),
        "xg_model": fit_xg_model(matches),
        "xt_grid": fit_xt(matches),
        "chaos_ref": fit_chaos_ref(matches),
    }
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.write_text(json.dumps(models, indent=1))
    pm = models["pass_model"]
    print(f"fitted on {args.matches} matches / {models['fitted_on']['events']} events")
    print("pass model:", dict(zip(pm["features"], pm["weights"])), "brier", pm["brier"])
    print("xG model:", models["xg_model"])
    print("xT max", max(map(max, models["xt_grid"])), "chaos_ref", models["chaos_ref"])


if __name__ == "__main__":
    main()
