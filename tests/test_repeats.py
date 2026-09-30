"""Repeated runs: mean, range, the median run as reference, and ties on the board."""
from __future__ import annotations

import json

from adebench import repeats


def run(when, door, updates=10.0, time_=10.0, abstention=10.0, live=None):
    secs = [{"name": "door", "weight": 25, "score": door / 25}, {"name": "updates", "weight": 10, "score": updates / 10},
            {"name": "time", "weight": 10, "score": time_ / 10}, {"name": "abstention", "weight": 10, "score": abstention / 10},
            {"name": "live_state", "weight": 10, "score": None if live is None else live / 10}]
    total = door + updates + time_ + abstention + (live or 0)
    return {"when": when, "total": round(total, 1), "measured_weight": 55 + (10 if live is not None else 0),
            "sections": secs}


def test_summary_mean_range_and_median_reference():
    runs = [run("2026-09-30T10:00:00", 18.8), run("2026-09-30T11:00:00", 15.6), run("2026-09-30T12:00:00", 18.8, live=10)]
    s = repeats.summarize(runs)
    assert s["builds"] == 3
    assert s["core"] == {"mean": 47.7, "min": 45.6, "max": 48.8, "weight": 55}
    assert s["reference"] == "2026-09-30T10:00:00"   # median by core, then total: 45.6, 48.8, 48.8 -> the middle one


def test_even_number_of_runs_takes_the_lower_median():
    s = repeats.summarize([run("a", 25.0), run("b", 15.6)])
    assert s["reference"] == "b"


def test_write_reads_the_runs_folder_and_sets_the_reference(tmp_path):
    folder = tmp_path / "x_report"
    (folder / "runs").mkdir(parents=True)
    for i, door in enumerate([18.8, 15.6, 21.9]):
        stem = f"2026093{i}-000000-aaaaaa"
        (folder / "runs" / f"{stem}.json").write_text(json.dumps(run(f"2026-09-3{i}T00:00:00", door)), encoding="utf-8")
        (folder / "runs" / f"{stem}.md").write_text(f"report {i}", encoding="utf-8")
    s = repeats.write(folder)
    saved = json.loads((folder / "repeats.json").read_text(encoding="utf-8"))
    assert saved["builds"] == 3 and saved["reference_file"] == "runs/20260930-000000-aaaaaa.json"
    assert (folder / "reference.md").read_text(encoding="utf-8") == "report 0"
    assert s["core"]["min"] == 45.6 and s["core"]["max"] == 51.9


def test_a_named_runs_folder_writes_its_own_files(tmp_path):
    folder = tmp_path / "x_report"
    (folder / "runs_gemini").mkdir(parents=True)
    (folder / "runs_gemini" / "r1.json").write_text(json.dumps(run("t", 20.0)), encoding="utf-8")
    (folder / "runs_gemini" / "r1.md").write_text("md", encoding="utf-8")
    repeats.write(folder, "runs_gemini")
    assert (folder / "repeats_gemini.json").exists() and (folder / "reference_gemini.json").exists()


def test_ties_use_the_wider_band_and_one_probe_at_least():
    board = [("a", 50.0, 0.0), ("b", 48.9, 0.0), ("c", 45.0, 0.0), ("d", 44.0, 4.0), ("e", 39.9, 0.0)]
    r = repeats.ranks([(mean, spread) for _, mean, spread in board])
    # a-b: 1.1 < one probe -> level; c is 5 below a -> behind; d swings 4 -> level with c, and e is 4.1 below d
    # (more than d's band of 4) -> behind d, but within c-e 5.1 > band 1.8 -> behind c
    assert r == [1, 1, 3, 3, 5]


def test_a_noisy_memory_never_ranks_above_a_higher_mean():
    # b's wide range ties it with a, c's narrow one does not; c has the higher mean,
    # so b cannot come out ahead of c
    board = [(36.3, 0.0), (34.4, 1.7), (34.2, 5.1)]
    assert repeats.ranks(board) == [1, 2, 2]
