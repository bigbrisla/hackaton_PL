"""Synthetic match event schema.

Coordinate convention (StatsBomb-like): pitch is 105 x 68 metres and every event's
x/y are expressed in the frame of the event's `team`, attacking toward x=105.
y=0 is that team's right touchline. To convert into the opponent's frame use
`flip(x, y)` (a 180 degree rotation).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0
GOAL_Y = PITCH_WIDTH / 2
GOAL_MOUTH = 7.32


def flip(x: float, y: float) -> tuple[float, float]:
    return PITCH_LENGTH - x, PITCH_WIDTH - y


class EventType(StrEnum):
    MATCH_START = "match_start"
    PERIOD_START = "period_start"
    PERIOD_END = "period_end"
    MATCH_END = "match_end"
    PASS = "pass"
    CARRY = "carry"
    SHOT = "shot"
    GOAL = "goal"
    SAVE = "save"
    PRESSURE = "pressure"
    TACKLE = "tackle"
    INTERCEPTION = "interception"
    FOUL = "foul"
    CARD = "card"
    BALL_OUT = "ball_out"
    SET_PIECE = "set_piece"
    PHYSICAL = "physical_update"


@dataclass
class Event:
    id: str
    match_id: str
    seq: int
    ts: float  # seconds of play since kick-off, monotonic across periods
    period: int
    period_clock: float  # seconds since the start of this period
    minute: int  # broadcast minute (45 / 90 during added time)
    added_minute: int  # 0 unless in added time
    type: EventType
    team_id: str | None = None
    player_id: str | None = None
    x: float | None = None
    y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    outcome: str | None = None
    under_pressure: bool = False
    possession_id: int | None = None
    possession_team_id: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["type"] = str(self.type)
        for k in ("x", "y", "end_x", "end_y", "ts", "period_clock"):
            if d[k] is not None:
                d[k] = round(d[k], 2)
        return d
