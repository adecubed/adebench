"""The private holdout: made outside the repo, frozen by hash, never printed."""
from __future__ import annotations

import json

import pytest

from adebench import holdout, registry
from tests.test_genset import SMALL_MIX, answer


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "holdout"
    monkeypatch.setenv("ADEBENCH_HOLDOUT", str(h))
    monkeypatch.setattr(holdout, "MANIFEST", tmp_path / "sets" / "holdout.json")
    monkeypatch.setattr(holdout, "MIX", SMALL_MIX)
    return h


def test_make_writes_the_set_privately_and_only_a_hash_publicly(home):
    said = []
    meta = holdout.make("v1", ask=lambda p: answer(), say=said.append)
    folder = home / "holdout-v1"
    assert (folder / "world.json").exists() and meta["version"] == "holdout-v1"
    manifest = json.loads(holdout.MANIFEST.read_text(encoding="utf-8"))
    assert set(manifest) == {"version", "sha256", "created", "mix"} and manifest["sha256"] == meta["sha256"]
    world = json.loads((folder / "world.json").read_text(encoding="utf-8"))
    assert world["canary"] and world["canary"] not in " ".join(said)


def test_make_never_overwrites(home):
    holdout.make("v1", ask=lambda p: answer(), say=lambda m: None)
    with pytest.raises(SystemExit):
        holdout.make("v1", ask=lambda p: answer(), say=lambda m: None)


def test_frozen_checks_the_hash(home):
    holdout.make("v1", ask=lambda p: answer(), say=lambda m: None)
    assert holdout.frozen().name == "holdout-v1"
    w = home / "holdout-v1" / "world.json"
    w.write_text(w.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(SystemExit, match="sha256"):
        holdout.frozen()


def test_frozen_names_both_versions_on_a_mismatch(home):
    holdout.make("v1", ask=lambda p: answer(), say=lambda m: None)
    m = json.loads(holdout.MANIFEST.read_text(encoding="utf-8"))
    m["version"] = "holdout-v2"
    holdout.MANIFEST.write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(SystemExit, match="holdout-v2"):
        holdout.frozen()


def test_the_private_folder_is_outside_every_repository(home):
    assert holdout.inside_a_repo(holdout.home()) is False
    assert holdout.inside_a_repo(holdout.ROOT / "sets")


def _tiny_holdout(home):
    # a real, valid set the synthetic memory can load: the quick set plus a canary, frozen
    import shutil
    from adebench import sets
    folder = home / "holdout-v1"
    shutil.copytree(holdout.ROOT / "sets" / "quick", folder)
    w = json.loads((folder / "world.json").read_text(encoding="utf-8"))
    w["canary"] = "cnrytest0001"
    w["facts"][0]["text"] += " (ref cnrytest0001)"
    (folder / "world.json").write_text(json.dumps(w), encoding="utf-8")
    holdout.MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    holdout.MANIFEST.write_text(json.dumps({"version": "holdout-v1", "sha256": sets.sha256(folder)}), encoding="utf-8")


def test_run_prints_only_scores_and_cleans_up(home, tmp_path):
    _tiny_holdout(home)
    said = []
    scores = holdout.run("synthetic", builds=2, say=said.append, roots=[tmp_path / "elsewhere"])
    assert len(scores) == 2 and all(0 <= s <= 55 for s in scores)
    out = " ".join(said)
    assert "cnrytest0001" not in out and "Brain" not in out and "8766" not in out
    assert len(list((home / "runs" / "holdout-v1" / "synthetic").glob("*.json"))) == 2
    assert not any((home / "stores").glob("synthetic-*"))


def test_run_fails_on_a_leak(home, tmp_path):
    _tiny_holdout(home)
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "cache.txt").write_text("cnrytest0001", encoding="utf-8")
    with pytest.raises(SystemExit, match="cache.txt"):
        holdout.run("synthetic", builds=1, say=lambda m: None, roots=[tmp_path / "elsewhere"])


def test_run_refuses_a_set_that_changed(home, tmp_path):
    _tiny_holdout(home)
    w = home / "holdout-v1" / "world.json"
    w.write_text(w.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(SystemExit, match="sha256"):
        holdout.run("synthetic", builds=1, say=lambda m: None, roots=[])


def test_a_failing_import_still_cleans_up(home, tmp_path, monkeypatch):
    _tiny_holdout(home)
    monkeypatch.setitem(registry.REGISTRY, "broken", {"adapter": "examples.synthetic:SyntheticAdapter",
                                                      "import": "examples/does_not_exist.py",
                                                      "store_env": None, "env": {}, "flags": []})
    with pytest.raises(SystemExit, match="import failed"):
        holdout.run("broken", builds=1, say=lambda m: None, roots=[])
    assert not any((home / "stores").glob("broken-*"))


def test_write_outcome_publishes_only_the_outcome(home, tmp_path):
    _tiny_holdout(home)
    holdout.run("synthetic", builds=1, say=lambda m: None, roots=[])
    pub = tmp_path / "pub"
    pub.mkdir()
    for f in (home / "runs" / "holdout-v1" / "synthetic").glob("*.json"):
        (pub / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "holdout.json"
    r = holdout.write_outcome("synthetic", pub, out=out)
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert saved == r and set(saved) == {"set", "sha256", "delta", "outcome", "x", "y", "public_builds", "private_builds"}
    assert saved["outcome"] == "no_drop"


def test_write_outcome_needs_public_runs(home, tmp_path):
    _tiny_holdout(home)
    (tmp_path / "empty").mkdir()
    with pytest.raises(SystemExit, match="no public2 runs"):
        holdout.write_outcome("synthetic", tmp_path / "empty", out=tmp_path / "h.json")
    assert not (tmp_path / "h.json").exists()


def test_the_default_private_folder_is_outside_every_repository():
    if not holdout.DEFAULT_HOME.parent.exists():
        pytest.skip("not the author's machine")
    assert holdout.inside_a_repo(holdout.DEFAULT_HOME) is False


def test_private_runs_are_kept_per_set_version(home, tmp_path):
    _tiny_holdout(home)
    holdout.run("synthetic", builds=1, say=lambda m: None, roots=[])
    assert len(list((home / "runs" / "holdout-v1" / "synthetic").glob("*.json"))) == 1
    stale = home / "runs" / "holdout-v0" / "synthetic"
    stale.mkdir(parents=True)
    (stale / "old.json").write_text('{"sections": []}', encoding="utf-8")
    pub = tmp_path / "pub"
    pub.mkdir()
    for f in (home / "runs" / "holdout-v1" / "synthetic").glob("*.json"):
        (pub / f.name).write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    assert holdout.write_outcome("synthetic", pub, out=tmp_path / "h.json")["private_builds"] == 1


def test_parent_benchmark_settings_do_not_reach_the_run(home, tmp_path, monkeypatch):
    _tiny_holdout(home)
    probe = tmp_path / "probe.py"
    probe.write_text("import os, sys\nsys.exit(1 if any(k.startswith(('ADEBENCH_DOOR', 'BRAIN_')) for k in os.environ) else 0)\n",
                     encoding="utf-8")
    monkeypatch.setenv("ADEBENCH_DOOR", "raw")
    monkeypatch.setenv("BRAIN_URL", "http://127.0.0.1:8766")
    monkeypatch.setitem(registry.REGISTRY, "probe", {"adapter": "examples.synthetic:SyntheticAdapter",
                                                     "import": str(probe), "store_env": None, "env": {},
                                                     "flags": ["--sections", "door", "--no-sandbox-test"]})
    holdout.run("probe", builds=1, say=lambda m: None, roots=[])


def test_extra_store_paths_are_cleaned_and_scanned(home, tmp_path, monkeypatch):
    _tiny_holdout(home)
    extra = tmp_path / "server_data"
    monkeypatch.setitem(registry.REGISTRY, "server", {"adapter": "examples.synthetic:SyntheticAdapter", "import": None,
                                                      "store_env": None, "env": {}, "cleanup": [str(extra)],
                                                      "flags": ["--sections", "door", "--no-sandbox-test"]})
    extra.mkdir()
    (extra / "db").write_text("x", encoding="utf-8")
    holdout.run("server", builds=1, say=lambda m: None, roots=[])
    assert not extra.exists()
