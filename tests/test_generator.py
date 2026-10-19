import statistics

import pytest

from generator.schema import PITCH_LENGTH, PITCH_WIDTH
from generator.simulate import simulate
from generator.teams import all_teams


@pytest.fixture(scope="module")
def matches():
    return [simulate("NBR", "HRV", seed) for seed in range(12)]


def test_deterministic_for_seed():
    a = [e.to_dict() for e in simulate("KMT", "ASV", 3)[1]]
    b = [e.to_dict() for e in simulate("KMT", "ASV", 3)[1]]
    assert a == b


def test_rosters_are_stable_and_unique():
    teams = all_teams()
    assert [p.name for p in teams[0].players] == [p.name for p in all_teams()[0].players]
    ids = [p.id for t in teams for p in t.players]
    assert len(ids) == len(set(ids))
    assert all(len(t.players) == 11 for t in teams)


def test_sequence_and_time_are_monotonic(matches):
    for _, events in matches:
        assert [e.seq for e in events] == list(range(len(events)))
        assert all(b.ts >= a.ts for a, b in zip(events, events[1:]))
        assert events[0].type == "match_start" and events[-1].type == "match_end"


def test_coordinates_in_bounds(matches):
    for _, events in matches:
        for e in events:
            for x, y in ((e.x, e.y), (e.end_x, e.end_y)):
                if x is not None:
                    assert 0 <= x <= PITCH_LENGTH and 0 <= y <= PITCH_WIDTH, e


def test_score_matches_goal_events(matches):
    for meta, events in matches:
        goals = [e for e in events if e.type == "goal"]
        for team_id, n in meta["final_score"].items():
            assert sum(g.team_id == team_id for g in goals) == n


def test_aggregates_are_football_realistic(matches):
    goals = statistics.mean(sum(m["final_score"].values()) for m, _ in matches)
    shots = statistics.mean(sum(e.type == "shot" for e in ev) for _, ev in matches)
    passes = [e for _, ev in matches for e in ev if e.type == "pass"]
    accuracy = sum(e.outcome == "complete" for e in passes) / len(passes)
    duration = statistics.mean(ev[-1].ts / 60 for _, ev in matches)
    assert 1.5 <= goals <= 4.5
    assert 18 <= shots <= 38
    assert 0.72 <= accuracy <= 0.88
    assert 92 <= duration <= 104
