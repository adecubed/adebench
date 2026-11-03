"""The board ranks on public2; quick is a second column; the holdout outcome is on each page."""
from __future__ import annotations

import json

import pytest

from adebench import repeats, site


def _report(door, cases=24):
    sec = lambda name, w, score, n: {"name": name, "weight": w, "score": score,  # noqa: E731
                                     "cases": [{"status": "PASS"}] * n}
    return {"when": "2026-10-03T00:00:00", "total": 40, "measured_weight": 65, "total_weight": 100,
            "sections": [sec("door", 25, door, cases), sec("updates", 10, 1, 9), sec("time", 10, 1, 9),
                         sec("abstention", 10, 0.5, 12)]}


@pytest.fixture
def examples(tmp_path, monkeypatch):
    monkeypatch.setattr(site, "ROOT", tmp_path)
    monkeypatch.setattr(site, "OUT", tmp_path / "site")
    monkeypatch.setattr(site, "ASSETS", tmp_path / "assets")
    return tmp_path / "examples"


def _write(examples, folder, name, d):
    f = examples / folder
    f.mkdir(parents=True, exist_ok=True)
    (f / f"{name}.json").write_text(json.dumps(d), encoding="utf-8")


def _row(name, **kw):
    facts = dict.fromkeys(("what", "access", "repo", "cfg", "model_on_write", "key", "where", "license",
                           "deterministic"), "")
    return {"name": name, "folder": f"{name.lower()}_report", **facts, **kw}


def _two(monkeypatch, second="B"):
    monkeypatch.setattr(site, "MEMORIES", [_row("A"), _row(second, pending="waits for a Docker host")])


def test_probe_is_the_core_weight_over_core_cases():
    assert repeats.probe_of(_report(0.5)) == pytest.approx(55 / (24 + 9 + 9 + 12), abs=0.01)


def test_ranks_take_the_set_probe():
    # 2 points apart: level with a 1.8 probe? no; with a 2.5 probe, yes
    assert repeats.ranks([(40.0, 0.0), (38.0, 0.0)]) == [1, 2]
    assert repeats.ranks([(40.0, 0.0), (38.0, 0.0)], probe=2.5) == [1, 1]


def test_ranked_on_public2_with_quick_beside(examples, monkeypatch):
    _two(monkeypatch)
    for folder, door_quick, door_p2 in (("a_report", 1.0, 0.4), ("b_report", 0.5, 0.9)):
        _write(examples, folder, "reference", _report(door_quick, 8))
        _write(examples, folder, "reference_public2", _report(door_p2))
    ranked, unranked = site.board_rows(site.loaded())
    assert [r["name"] for r in ranked] == ["B", "A"] and unranked == []
    assert ranked[0]["quick_core"] < ranked[1]["quick_core"]


def test_unranked_memories_keep_their_quick_number(examples, monkeypatch):
    _two(monkeypatch, "D")
    _write(examples, "a_report", "reference_public2", _report(0.5))
    _write(examples, "a_report", "reference", _report(0.5, 8))
    _write(examples, "d_report", "reference", _report(0.9, 8))
    ranked, unranked = site.board_rows(site.loaded())
    assert [r["name"] for r in ranked] == ["A"] and [r["name"] for r in unranked] == ["D"]
    assert unranked[0]["quick_core"] > 0


def test_public2_rows_share_the_memory_config(examples):
    _write(examples, "x_report", "memory_gemini", {"version": "1"})
    assert site.load_config("x_report", "reference_gemini_public2") == {"version": "1"}


def test_the_holdout_outcome_is_read_per_row(examples):
    _write(examples, "x_report", "holdout_gemini", {"outcome": "no_drop", "y": 4.1})
    assert site.load_holdout("x_report", "reference_gemini")["y"] == 4.1
    assert site.load_holdout("x_report", "reference") is None


def test_holdout_line_says_lower_or_no_drop_without_judging():
    base = {"delta": 3.0, "shift": -1.8, "others": 4, "public_builds": 3, "private_builds": 1,
            "set": "holdout-v1", "sha256": "3cd42b9f" + "0" * 56}
    lower = site.holdout_line(dict(base, outcome="lower", x=-6.0, y=3.1))
    same = site.holdout_line(dict(base, outcome="no_drop", x=None, y=5.7))
    assert lower.startswith("lower by 6.0 core points") and same.startswith("no drop detected (±5.7)")
    assert "shift −1.8 from 4 other memories" in lower and "holdout-v1 3cd42b9f" in lower
    for word in ("tuned", "overfit", "cheat"):
        assert word not in lower + same
    assert site.holdout_line(None) == "not run yet"


def test_the_board_shows_quick_the_unranked_table_and_the_holdout(examples, monkeypatch):
    _two(monkeypatch, "D")
    _write(examples, "a_report", "reference_public2", _report(0.5))
    _write(examples, "a_report", "reference", _report(0.5, 8))
    _write(examples, "a_report", "holdout", {"outcome": "no_drop", "x": None, "y": 5.7, "delta": 3.0,
                                             "shift": -1.8, "others": 4, "public_builds": 3,
                                             "private_builds": 1, "set": "holdout-v1", "sha256": "ab" * 32})
    _write(examples, "d_report", "reference", _report(0.9, 8))
    site.build()
    index = (site.OUT / "index.html").read_text(encoding="utf-8")
    assert "Quick &middot; 55" in index and "public2" in index
    assert "Not yet run on public2" in index and "waits for a Docker host" in index
    assert "no drop detected (±5.7)" in (site.OUT / "a" / "index.html").read_text(encoding="utf-8")
    # an unranked memory keeps its page, on its quick numbers
    assert (site.OUT / "d" / "index.html").exists()


def test_a_public2_config_of_its_own_wins(examples):
    # a memory run on public2 with another version than its quick run declares it apart
    _write(examples, "x_report", "memory", {"version": "quick one"})
    _write(examples, "x_report", "memory_public2", {"version": "public2 one"})
    assert site.load_config("x_report", "reference_public2") == {"version": "public2 one"}
    assert site.load_config("x_report", "reference") == {"version": "quick one"}
