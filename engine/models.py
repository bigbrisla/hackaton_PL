"""Statistical models fitted on synthetic matches (see engine/fit.py).

- xG: location + body-part logistic model.
- Pass success: logistic regression on pass geometry and pressure -> difficulty rating 0-100.
- xT: expected-threat grid computed by value iteration over synthetic possession chains.

All coordinates are in the acting team's frame (attacking toward x=105).
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

PITCH_LENGTH, PITCH_WIDTH, GOAL_Y, GOAL_MOUTH = 105.0, 68.0, 34.0, 7.32
XT_COLS, XT_ROWS = 16, 12
MODEL_PATH = Path(__file__).parent / "data" / "models.json"

FEATURE_NAMES = ["bias", "length_over_12m", "under_pressure", "into_box", "final_third_target",
                 "forward_progress", "cross", "lofted", "own_third_start"]


def flip(x: float, y: float) -> tuple[float, float]:
    return PITCH_LENGTH - x, PITCH_WIDTH - y


def in_box(x: float, y: float) -> bool:
    return x > 88.5 and abs(y - GOAL_Y) < 20.16


def sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-max(-30.0, min(30.0, z))))


def shot_features(x: float, y: float, body_part: str = "foot") -> list[float]:
    d = math.hypot(PITCH_LENGTH - x, GOAL_Y - y)
    angle = abs(math.atan2(GOAL_MOUTH / 2, max(d, 0.5)) * 2)
    return [1.0, d / 10, angle, float(body_part == "head")]


def xg(x: float, y: float, body_part: str = "foot") -> float:
    w = load_models()["xg_model"]["weights"]
    return sigmoid(sum(a * b for a, b in zip(w, shot_features(x, y, body_part))))


def pass_features(x: float, y: float, ex: float, ey: float, under_pressure: bool,
                  height: str | None = None) -> list[float]:
    length = math.hypot(ex - x, ey - y)
    if height is None:
        height = "high" if length > 32 else "low" if length > 18 else "ground"
    cross = x > 75 and (y < 16 or y > 52) and ex > 88
    return [
        1.0,
        max(0.0, length - 12) / 10,
        float(under_pressure),
        float(in_box(ex, ey)),
        float(ex > 75),
        max(0.0, ex - x) / 20,
        float(cross),
        float(height == "high"),
        float(x < 30),
    ]


@lru_cache(maxsize=1)
def load_models() -> dict:
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"{MODEL_PATH} missing: run `python -m engine.fit` first")
    return json.loads(MODEL_PATH.read_text())


def pass_success(feats: list[float]) -> float:
    w = load_models()["pass_model"]["weights"]
    return sigmoid(sum(a * b for a, b in zip(w, feats)))


def pass_difficulty(feats: list[float]) -> int:
    """0 = trivial, 100 = near impossible."""
    return round(100 * (1 - pass_success(feats)))


def xt_cell(x: float, y: float) -> tuple[int, int]:
    c = min(XT_COLS - 1, max(0, int(x / PITCH_LENGTH * XT_COLS)))
    r = min(XT_ROWS - 1, max(0, int(y / PITCH_WIDTH * XT_ROWS)))
    return c, r


def xt(x: float, y: float) -> float:
    c, r = xt_cell(x, y)
    return load_models()["xt_grid"][r][c]


def option_value(x: float, y: float, tx: float, ty: float, under_pressure: bool) -> tuple[float, float]:
    """Expected value of passing from (x, y) to (tx, ty): success * threat gained - failure * threat conceded.

    Returns (expected_value, success_probability).
    """
    p = pass_success(pass_features(x, y, tx, ty, under_pressure))
    lost_x, lost_y = flip(tx, ty)
    return p * xt(tx, ty) - (1 - p) * xt(lost_x, lost_y), p
