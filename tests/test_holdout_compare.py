"""The holdout outcome: lower by X, or no drop detected (±Y)."""
from __future__ import annotations

from adebench import holdout_compare as hc


def run(door, updates=(1, 1, 1), time_=(1, 1, 1, 1, 1, 1), abstention=(1, 1, 1, 1), skip_time=False):
    def sec(name, weight, bits):
        return {"name": name, "weight": weight,
                "cases": [{"status": "PASS" if b else "FAIL"} for b in bits] + [{"status": "SKIP"}]}
    secs = [sec("door", 25, door), sec("updates", 10, updates), sec("abstention", 10, abstention)]
    if not skip_time:
        secs.append(sec("time", 10, time_))
    return {"sections": secs}


def test_core55_rescales_over_the_sections_present():
    assert hc.core55(hc.core_cases(run([1] * 24))) == 55.0
    assert hc.core55(hc.core_cases(run([1] * 24, skip_time=True))) == 55.0
    assert hc.core55(hc.core_cases(run([1] * 12 + [0] * 12))) == 42.5


def test_same_memory_same_questions_shows_no_drop():
    pub = [run([1] * 20 + [0] * 4)] * 5
    r = hc.compare(pub, pub[:3])
    assert r["outcome"] == "no_drop" and r["x"] is None and r["y"] > 0


def test_a_clear_drop_is_lower_by_about_the_gap():
    pub = [run([1] * 22 + [0] * 2)] * 5
    priv = [run([1] * 8 + [0] * 16, abstention=(0, 0, 0, 1))] * 3
    r = hc.compare(pub, priv)
    assert r["outcome"] == "lower" and r["x"] < -3


def test_a_higher_private_score_is_no_drop():
    r = hc.compare([run([1] * 8 + [0] * 16)] * 3, [run([1] * 24)])
    assert r["outcome"] == "no_drop"


def test_harness_probes_are_not_resampled():
    # updates and time come from the harness, the same on every set: a run whose only
    # difference is an updates failure gives a fixed gap, not a spread
    pub = [run([1] * 24)] * 3
    priv = [run([1] * 24, updates=(1, 1, 0))] * 3
    assert hc.compare(pub, priv)["y"] == 0.0


def test_the_result_carries_counts_not_cases():
    r = hc.compare([run([1] * 24)] * 3, [run([1] * 24)])
    assert set(r) == {"outcome", "x", "y", "delta", "public_builds", "private_builds"}
    assert r["public_builds"] == 3 and r["private_builds"] == 1


def test_a_run_without_door_cases_is_refused():
    import pytest
    empty = {"sections": [{"name": "door", "weight": 25, "cases": [{"status": "SKIP"}]}]}
    with pytest.raises(ValueError, match="door"):
        hc.compare([run([1] * 24)] * 3, [empty])


def test_both_sides_are_scored_on_the_sections_they_share():
    # time SKIPs on the public side: a private run failing time must not read as a drop,
    # because the two sides would then be scored on different sections
    pub = [run([1] * 24, skip_time=True)] * 3
    priv = [run([1] * 24, time_=(0, 0, 0, 0, 0, 0))] * 3
    assert hc.compare(pub, priv)["outcome"] == "no_drop"
