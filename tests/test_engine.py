import pytest

from engine.core import MatchEngine
from engine.models import pass_difficulty, pass_features, xg, xt
from generator.simulate import simulate


@pytest.fixture(scope="module")
def run():
    meta, events = simulate("NBR", "HRV", 7)
    engine = MatchEngine(meta)
    out = [m for e in events for m in engine.ingest(e.to_dict())]
    return meta, engine, out


def test_threat_and_xg_grow_toward_goal():
    assert xt(100, 34) > xt(70, 34) > xt(20, 34)
    assert xg(99, 34) > xg(90, 34) > xg(80, 34)
    assert xg(99, 34, "head") < xg(99, 34)


def test_pass_difficulty_rises_with_pressure_length_and_box():
    easy = pass_difficulty(pass_features(40, 34, 50, 34, False))
    assert pass_difficulty(pass_features(40, 34, 50, 34, True)) > easy
    assert pass_difficulty(pass_features(40, 34, 80, 34, False)) > easy
    assert pass_difficulty(pass_features(80, 34, 95, 34, False)) > pass_difficulty(pass_features(80, 34, 85, 34, False))
    assert 0 <= easy <= 100


def test_engine_score_and_possession_match_the_feed(run):
    meta, engine, _ = run
    assert engine.score == meta["final_score"]
    home, away = engine.team_summary(engine.home_id), engine.team_summary(engine.away_id)
    assert abs(home["possession"] + away["possession"] - 1) < 1e-6


def test_one_goal_moment_per_goal_with_explainable_facts(run):
    meta, _, out = run
    goals = [m for m in out if m["kind"] == "moment" and m["type"] == "goal"]
    assert len(goals) == sum(meta["final_score"].values())
    for g in goals:
        assert {"xg", "shot_speed_kmh", "build_up_passes"} <= g["facts"].keys()
        assert g["player"] and g["team"]


def test_chaos_is_a_bounded_percentile(run):
    readings = [m["chaos"]["chaos"] for m in out_states(run) if m["chaos"]]
    assert readings and all(0 <= c <= 100 for c in readings)
    assert 25 < sum(readings) / len(readings) < 75


def test_dva_never_positive_and_best_option_present(run):
    for m in run[2]:
        if m["kind"] == "event" and "dva" in m["enriched"]:
            assert m["enriched"]["dva"] <= 0
            assert m["enriched"]["best_option"]["player_id"]


def test_overlays_are_timed(run):
    overlays = [m for m in run[2] if m["kind"] == "overlay"]
    assert overlays
    for o in overlays:
        assert o["out_ts"] > o["in_ts"] and o["layer"] and o["template"]


def out_states(run):
    return [m for m in run[2] if m["kind"] == "state"]
