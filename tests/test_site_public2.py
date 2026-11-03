"""The board ranks on quick as before; public2 is a column beside it; the holdout outcome is on each page."""
from __future__ import annotations

import json

import pytest

from adebench import site


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


def test_ranked_on_quick_with_public2_beside(examples, monkeypatch):
    _two(monkeypatch)
    for folder, door_quick, door_p2 in (("a_report", 1.0, 0.4), ("b_report", 0.5, 0.9)):
        _write(examples, folder, "reference", _report(door_quick, 8))
        _write(examples, folder, "reference_public2", _report(door_p2))
    rows = site.board_rows(site.loaded())
    assert [r["name"] for r in rows] == ["A", "B"]   # quick decides, public2 does not move it
    assert rows[0]["p2_core"] < rows[1]["p2_core"]


def test_a_memory_without_public2_stays_on_the_board(examples, monkeypatch):
    _two(monkeypatch, "D")
    _write(examples, "a_report", "reference_public2", _report(0.5))
    _write(examples, "a_report", "reference", _report(0.5, 8))
    _write(examples, "d_report", "reference", _report(0.9, 8))
    rows = site.board_rows(site.loaded())
    assert [r["name"] for r in rows] == ["D", "A"]
    assert rows[0]["p2_core"] is None and rows[1]["p2_core"] > 0


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


def test_the_board_shows_public2_beside_and_the_holdout_on_the_page(examples, monkeypatch):
    _two(monkeypatch, "D")
    _write(examples, "a_report", "reference_public2", _report(0.5))
    _write(examples, "a_report", "reference", _report(0.5, 8))
    _write(examples, "a_report", "holdout", {"outcome": "no_drop", "x": None, "y": 5.7, "delta": 3.0,
                                             "shift": -1.8, "others": 4, "public_builds": 3,
                                             "private_builds": 1, "set": "holdout-v1", "sha256": "ab" * 32})
    _write(examples, "d_report", "reference", _report(0.9, 8))
    site.build()
    index = (site.OUT / "index.html").read_text(encoding="utf-8")
    assert "public2 &middot; 55" in index and "synthetic golden set" in index
    assert '<th class="n">public2 &middot; 55</th>' in index   # shown on a phone too
    assert "waits for a Docker host" in index and "Not yet run" not in index
    assert "no drop detected (±5.7)" in (site.OUT / "a" / "index.html").read_text(encoding="utf-8")
    assert (site.OUT / "d" / "index.html").exists()


def test_a_public2_config_of_its_own_wins(examples):
    # a memory run on public2 with another version than its quick run declares it apart
    _write(examples, "x_report", "memory", {"version": "quick one"})
    _write(examples, "x_report", "memory_public2", {"version": "public2 one"})
    assert site.load_config("x_report", "reference_public2") == {"version": "public2 one"}
    assert site.load_config("x_report", "reference") == {"version": "quick one"}
