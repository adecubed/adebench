# The private holdout — Implementation Plan (2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate and freeze a private set nobody reads, run a memory on it in isolation printing only aggregates, detect any leak of it, and tell whether a memory's score drops on it.

**Architecture:** `adebench/holdout.py` owns the private folder (`C:/Users/simon/adebench_holdout`, or `ADEBENCH_HOLDOUT`): `make` generates a set there with `genset` (canary on) and writes a public manifest `sets/holdout.json` (version and sha256 only); `run` loads a memory from a registry entry into a fresh store, runs `python -m adebench` in a subprocess with all its output captured into the private folder, deletes the store, scans for the canary, and prints only core scores. `adebench/leaks.py` scans folders for the canary. `adebench/holdout_compare.py` turns public and private runs into an outcome (lower by X / no drop detected ±Y) with a bootstrap over runs and the set's own cases, and writes `examples/<memory>_report/holdout.json`. Wiring the 14 real memories into the registry belongs to plan 3; here the registry has the in-process synthetic memory, which every test uses.

**Tech Stack:** Python 3.11, standard library only, pytest.

**Spec:** `docs/specs/2026-09-30-sets-and-holdout-design.md`, sections 4 and 5.

## Global Constraints

- Zero third-party dependencies in `adebench/`.
- Everything public is in English.
- Never commit or push without the user's explicit ok: at the end, show files and message and wait.
- The private folder is never inside a repository and never inside `adebench_locale` or the orchestrator.
- No command of this plan prints a private question, answer, world item, report line or canary: only counts, core scores, outcomes, versions and sha256.
- A private set is never overwritten: a new one is `holdout-v2`.
- Outcome rule (one-sided, spec section 4 as amended 2026-09-30): 90 % interval of `private − public2` core points (per 55) from 2,000 resamples that pick a run on each side and resample only the door and abstention cases; δ = 3. "lower" by X if the interval lies wholly below 0 and its midpoint is below −δ (X = midpoint); otherwise "no drop detected" with Y = the interval's half-width.
- Published per memory: outcome, X or Y, δ, set version and sha256, number of builds on each side. Nothing else about the private runs.

## Review Focus

- A registry entry whose import script fails: the store must still be deleted and the leak scan still run; the run reports the failure without the script's output (Task 4).
- The canary found inside the private folder itself: not a leak (the private folder is excluded from the scan) (Task 3).
- Private runs with a different number of core cases than public runs (sections SKIP on one side): the comparison must work per 55 points, not per case count (Task 2).
- `run` launched with the holdout manifest in the repo pointing at another version than the folder: refuse, naming both versions, without loading anything (Task 4).
- A memory with no public2 runs yet: `compare` says so and writes nothing (Task 5).

---

### Task 1: The private folder, `make` and the manifest

**Files:**
- Create: `adebench/holdout.py`
- Create: `tests/test_holdout.py`

**Interfaces:**
- Consumes: `genset.generate(out, name, seed, ask, mix, attempts, say, model, canary)`, `genset.gemini(model)`, `sets.sha256(path)`, `validate_set.MIX_PUBLIC`.
- Produces: `holdout.home() -> Path` (env `ADEBENCH_HOLDOUT` or `C:/Users/simon/adebench_holdout`); `holdout.MANIFEST = ROOT / "sets" / "holdout.json"`; `holdout.make(version: str, ask, say=print, h: Path | None = None) -> dict` (writes `<home>/holdout-<version>/` and the manifest `{"version": "holdout-<version>", "sha256": ..., "created": ..., "mix": "MIX_PUBLIC"}`); `holdout.frozen(h: Path | None = None) -> Path` (the set folder named by the manifest, after checking its sha256; raises `SystemExit` naming both versions or both hashes on a mismatch).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_holdout.py
"""The private holdout: made outside the repo, frozen by hash, never printed."""
from __future__ import annotations

import json

import pytest

from adebench import holdout
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest tests/test_holdout.py -q`
Expected: collection error, `holdout` not found.

- [ ] **Step 3: Implement `adebench/holdout.py` (first part)**

```python
# adebench/holdout.py
"""The private holdout set (spec sections 4-5).

    python -m adebench.holdout make --version v1          # generate and freeze, prints only the hash
    python -m adebench.holdout run --memory synthetic --builds 1
    python -m adebench.holdout compare --memory synthetic

The set lives outside every repository (ADEBENCH_HOLDOUT, default
C:/Users/simon/adebench_holdout); the repository keeps only its version
and sha256 (sets/holdout.json). Nothing here prints a question, an answer,
a world item or a report line: only counts, core scores and outcomes.
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from adebench import genset, sets, validate_set

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "sets" / "holdout.json"
MIX = validate_set.MIX_PUBLIC
DEFAULT_HOME = Path("C:/Users/simon/adebench_holdout")


def home() -> Path:
    return Path(os.environ.get("ADEBENCH_HOLDOUT") or DEFAULT_HOME)


def inside_a_repo(path: Path) -> bool:
    return any((p / ".git").exists() for p in [Path(path).resolve(), *Path(path).resolve().parents])


def make(version: str, ask, say=print, h: Path | None = None) -> dict:
    h = h or home()
    if inside_a_repo(h):
        raise SystemExit(f"{h} is inside a repository: the private set must live outside")
    name = f"holdout-{version}"
    meta = genset.generate(h / name, name, secrets.randbelow(10**9), ask=ask, mix=MIX, say=say,
                           model="gemini-3-flash-preview", canary=True)
    manifest = {"version": name, "sha256": meta["sha256"],
                "created": datetime.now(timezone.utc).isoformat(timespec="seconds"), "mix": "MIX_PUBLIC"}
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return {**meta, "version": name}


def frozen(h: Path | None = None) -> Path:
    h = h or home()
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    folder = h / m["version"]
    if not (folder / "set.json").exists():
        local = sorted(p.name for p in h.glob("holdout-*"))
        raise SystemExit(f"the manifest names {m['version']}, the private folder has {local or 'nothing'}")
    got = sets.sha256(folder)
    if got != m["sha256"]:
        raise SystemExit(f"{m['version']}: sha256 {got[:12]} does not match the manifest's {m['sha256'][:12]}")
    return folder
```

Note: `make`'s parameter for the folder is `h`, but the tests call `make("v1", ask=..., say=...)` and rely on `ADEBENCH_HOLDOUT`; keep the keyword name `h` as written.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_holdout.py -q`
Expected: 5 passed.

---

### Task 2: The comparison

**Files:**
- Create: `adebench/holdout_compare.py`
- Create: `tests/test_holdout_compare.py`

**Interfaces:**
- Consumes: report JSON dicts as adebench writes them (`sections[*].name/weight/cases[*].status`).
- Produces: `holdout_compare.core_cases(run: dict) -> dict[str, list[bool]]` (per core section, the pass/fail of each measured case: PASS → True, FAIL/ERROR → False, SKIP dropped); `holdout_compare.core55(cases: dict[str, list[bool]]) -> float` (core points per 55 from those cases, with the section weights door 25, updates 10, time 10, abstention 10, rescaled to 55 over the sections present); `holdout_compare.compare(public: list[dict], private: list[dict], delta: float = 3.0, n: int = 2000, seed: int = 0) -> dict` returning `{"outcome": "lower"|"no_drop", "x": float | None, "y": float, "delta": delta, "public_builds": int, "private_builds": int}` (x only for "lower"; y the interval's half-width); `holdout_compare.SET_SECTIONS = {"door", "abstention"}`, the only sections resampled.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_holdout_compare.py
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest tests/test_holdout_compare.py -q`
Expected: collection error.

- [ ] **Step 3: Implement**

```python
# adebench/holdout_compare.py
"""Does a memory's core score drop on the private set? (spec section 4)

Each resample picks one public run and one private run at random (the spread
of builds) and resamples, with replacement, the cases of the sections that
come from the set's questions, door and abstention (the spread of questions);
updates and time are mostly probes the harness writes itself, the same on
every set, and are kept as the run has them. The 90 % interval of private
minus public, per 55 core points, decides: "lower" by X when it lies wholly
below 0 and its midpoint is below -delta, otherwise "no drop detected" with
Y, the interval's half-width. The check is one-sided: a set of this size can
show a drop, not that two scores are equal within a few points.
"""
from __future__ import annotations

import random

WEIGHTS = {"door": 25, "updates": 10, "time": 10, "abstention": 10}
SET_SECTIONS = {"door", "abstention"}


def core_cases(run: dict) -> dict[str, list[bool]]:
    out = {}
    for s in run.get("sections", []):
        if s.get("name") in WEIGHTS:
            bits = [c.get("status") == "PASS" for c in s.get("cases", []) if c.get("status") != "SKIP"]
            if bits:
                out[s["name"]] = bits
    return out


def core55(cases: dict[str, list[bool]]) -> float:
    w = sum(WEIGHTS[k] for k in cases)
    if not w:
        return 0.0
    pts = sum(WEIGHTS[k] * sum(v) / len(v) for k, v in cases.items())
    return round(pts * 55 / w, 4)


def _resample(cases: dict[str, list[bool]], rng: random.Random) -> dict[str, list[bool]]:
    return {k: ([rng.choice(v) for _ in v] if k in SET_SECTIONS else v) for k, v in cases.items()}


def compare(public: list[dict], private: list[dict], delta: float = 3.0, n: int = 2000, seed: int = 0) -> dict:
    rng = random.Random(seed)
    pub = [core_cases(r) for r in public]
    priv = [core_cases(r) for r in private]
    diffs = sorted(core55(_resample(rng.choice(priv), rng)) - core55(_resample(rng.choice(pub), rng))
                   for _ in range(n))
    lo, hi = diffs[int(0.05 * n)], diffs[int(0.95 * n) - 1]
    mid = round((lo + hi) / 2, 1)
    lower = hi < 0 and mid < -delta
    return {"outcome": "lower" if lower else "no_drop", "x": mid if lower else None,
            "y": round((hi - lo) / 2, 1), "delta": delta,
            "public_builds": len(public), "private_builds": len(private)}
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_holdout_compare.py -q`
Expected: 7 passed.

---

### Task 3: The leak scan

**Files:**
- Create: `adebench/leaks.py`
- Create: `tests/test_leaks.py`

**Interfaces:**
- Produces: `leaks.DEFAULT_ROOTS: list[Path]` (the adebench repo, the orchestrator repo `C:/Users/simon/OneDrive/Documenti/GitHub/ade_desktop_orchestrator` if it exists, `C:/Users/simon/ade/bench_memories`, the memories' default homes `~/.mem0`, `~/.cognee`, `~/.engram`, `~/.agentmemory`, `~/.memu`, `~/.gbrain`, `~/.memoose`, the session transcripts `~/.claude/projects`, and the system temp folder); `leaks.scan(token: str, roots: list[Path], exclude: list[Path], max_bytes: int = 20_000_000) -> list[Path]` (files containing the token, as bytes, skipping excluded trees, files over `max_bytes`, and model weights `.safetensors .bin .onnx .gguf .pt`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_leaks.py
"""The canary scan: found anywhere but the private folder is a leak."""
from __future__ import annotations

from adebench import leaks


def test_finds_the_token_and_names_the_file(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "log.txt").write_text("x cnryabc123 y", encoding="utf-8")
    (tmp_path / "a" / "clean.txt").write_text("nothing", encoding="utf-8")
    assert leaks.scan("cnryabc123", [tmp_path], exclude=[]) == [tmp_path / "a" / "log.txt"]


def test_the_private_folder_is_not_a_leak(tmp_path):
    priv = tmp_path / "holdout"
    priv.mkdir()
    (priv / "world.json").write_text("cnryabc123", encoding="utf-8")
    assert leaks.scan("cnryabc123", [tmp_path], exclude=[priv]) == []


def test_weights_and_huge_files_are_skipped(tmp_path):
    (tmp_path / "m.safetensors").write_bytes(b"cnryabc123")
    (tmp_path / "big.log").write_bytes(b"cnryabc123" + b"0" * 100)
    assert leaks.scan("cnryabc123", [tmp_path], exclude=[], max_bytes=50) == []


def test_missing_roots_are_fine(tmp_path):
    assert leaks.scan("cnryabc123", [tmp_path / "nope"], exclude=[]) == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest tests/test_leaks.py -q`
Expected: collection error.

- [ ] **Step 3: Implement**

```python
# adebench/leaks.py
"""Search for the private set's canary anywhere it must not be (spec section 5)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

HOME = Path.home()
DEFAULT_ROOTS = [Path(__file__).resolve().parents[1],
                 Path("C:/Users/simon/OneDrive/Documenti/GitHub/ade_desktop_orchestrator"),
                 Path("C:/Users/simon/ade/bench_memories"),
                 *(HOME / d for d in (".mem0", ".cognee", ".engram", ".agentmemory", ".memu", ".gbrain", ".memoose")),
                 HOME / ".claude" / "projects", Path(tempfile.gettempdir())]
WEIGHTS = {".safetensors", ".bin", ".onnx", ".gguf", ".pt"}


def scan(token: str, roots: list[Path], exclude: list[Path], max_bytes: int = 20_000_000) -> list[Path]:
    needle = token.encode()
    skip = [Path(e).resolve() for e in exclude]
    hits = []
    for root in roots:
        root = Path(root)
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            here = Path(dirpath).resolve()
            if any(here == s or s in here.parents for s in skip):
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d != ".git"]
            for f in filenames:
                p = Path(dirpath) / f
                try:
                    if p.suffix in WEIGHTS or p.stat().st_size > max_bytes:
                        continue
                    if needle in p.read_bytes():
                        hits.append(p)
                except OSError:
                    continue
    return sorted(hits)
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_leaks.py -q`
Expected: 4 passed.

---

### Task 4: The isolated runner

**Files:**
- Modify: `adebench/holdout.py` (add `REGISTRY`, `run`, `main`)
- Modify: `tests/test_holdout.py`

**Interfaces:**
- Consumes: `holdout.frozen()` (Task 1), `leaks.scan`, `leaks.DEFAULT_ROOTS` (Task 3), `holdout_compare.core_cases`, `holdout_compare.core55` (Task 2).
- Produces: `holdout.REGISTRY: dict[str, dict]` — an entry is `{"adapter": "module:Class", "import": "examples/x_import.py" | None, "store_env": "VAR" | None, "env": {..}, "flags": [..]}`; plan 3 adds the real memories. `holdout.run(memory: str, builds: int = 1, say=print, roots: list[Path] | None = None) -> list[float]` (the core per 55 of each build; runs go to `<home>/runs/<memory>/`, logs to `<home>/logs/`, stores to `<home>/stores/<memory>-<n>/`, deleted after each build; raises `SystemExit` naming the files if the canary is found outside the private folder). CLI `python -m adebench.holdout make|run|compare`.

- [ ] **Step 1: Write the failing tests (append to `tests/test_holdout.py`)**

```python
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
    assert len(list((home / "runs" / "synthetic").glob("*.json"))) == 2
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
    monkeypatch.setitem(holdout.REGISTRY, "broken", {"adapter": "examples.synthetic:SyntheticAdapter",
                                                      "import": "examples/does_not_exist.py",
                                                      "store_env": None, "env": {}, "flags": []})
    said = []
    with pytest.raises(SystemExit, match="import failed"):
        holdout.run("broken", builds=1, say=said.append, roots=[])
    assert not any((home / "stores").glob("broken-*"))
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest tests/test_holdout.py -q`
Expected: the four new tests fail (`run` / `REGISTRY` missing).

- [ ] **Step 3: Implement (append to `adebench/holdout.py`)**

```python
import shutil
import subprocess
import sys

from adebench import holdout_compare, leaks

# how to load and run each memory on the private set; plan 3 adds the real memories.
# store_env: the variable through which the memory takes its data folder (the runner
# points it at a fresh folder under <home>/stores and deletes it afterwards).
REGISTRY: dict[str, dict] = {
    "synthetic": {"adapter": "examples.synthetic:SyntheticAdapter", "import": None, "store_env": None,
                  "env": {}, "flags": ["--sections", "door", "updates", "time", "abstention", "--no-sandbox-test"]},
}


def _python(args: list[str], env: dict, log) -> int:
    return subprocess.call([sys.executable, *args], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)


def run(memory: str, builds: int = 1, say=print, roots: list[Path] | None = None) -> list[float]:
    entry = REGISTRY.get(memory)
    if entry is None:
        raise SystemExit(f"no registry entry for {memory!r}")
    folder = frozen()
    h = home()
    world = json.loads((folder / "world.json").read_text(encoding="utf-8"))
    runs_dir, logs, stores = h / "runs" / memory, h / "logs", h / "stores"
    for d in (runs_dir, logs, stores):
        d.mkdir(parents=True, exist_ok=True)
    scores = []
    for b in range(1, builds + 1):
        store = stores / f"{memory}-{b}"
        shutil.rmtree(store, ignore_errors=True)
        store.mkdir()
        env = {**os.environ, **entry["env"], "ADEBENCH_SET": str(folder), "ADEBENCH_LIVE_STATE_KEY": "",
               "PYTHONIOENCODING": "utf-8"}
        if entry["store_env"]:
            env[entry["store_env"]] = str(store)
        before = set(runs_dir.glob("*.json"))
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            with open(logs / f"{memory}-{stamp}-{b}.log", "w", encoding="utf-8") as log:
                if entry["import"] and _python([entry["import"]], env, log) != 0:
                    raise SystemExit(f"{memory} build {b}: import failed (log in the private folder)")
                code = _python(["-m", "adebench", "--adapter", entry["adapter"], "--cases", str(folder / "cases"),
                                "--repo", str(folder / "repo"), "--history", str(runs_dir), *entry["flags"]], env, log)
            new = sorted(set(runs_dir.glob("*.json")) - before)
            if code != 0 or not new:
                raise SystemExit(f"{memory} build {b}: benchmark failed (log in the private folder)")
            report = json.loads(new[-1].read_text(encoding="utf-8"))
            scores.append(round(holdout_compare.core55(holdout_compare.core_cases(report)), 1))
            say(f"{memory} build {b}: core {scores[-1]} / 55")
        finally:
            shutil.rmtree(store, ignore_errors=True)
            hits = leaks.scan(world["canary"], leaks.DEFAULT_ROOTS if roots is None else roots, exclude=[h])
            if hits:
                raise SystemExit("private set leaked into: " + ", ".join(str(p) for p in hits))
    return scores


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="adebench.holdout")
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make")
    mk.add_argument("--version", required=True)
    rn = sub.add_parser("run")
    rn.add_argument("--memory", required=True)
    rn.add_argument("--builds", type=int, default=1)
    cp = sub.add_parser("compare")
    cp.add_argument("--memory", required=True)
    cp.add_argument("--public", help="folder of the memory's public2 runs")
    a = ap.parse_args(argv)
    if a.cmd == "make":
        m = make(a.version, genset.gemini("gemini-3-flash-preview"))
        print(f"{m['version']} frozen, sha256 {m['sha256'][:12]}")
    elif a.cmd == "run":
        run(a.memory, a.builds)
    else:
        from adebench import holdout_compare as hc  # noqa: F401  (Task 5 adds write())
        write_outcome(a.memory, Path(a.public) if a.public else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_holdout.py -q`
Expected: 9 passed. The synthetic memory runs in a subprocess; each build takes a few seconds.

---

### Task 5: The published outcome

**Files:**
- Modify: `adebench/holdout.py` (add `write_outcome`)
- Modify: `tests/test_holdout.py`

**Interfaces:**
- Consumes: `holdout_compare.compare` (Task 2); private runs in `<home>/runs/<memory>/*.json` (Task 4); public runs in `examples/<folder>_report/runs_public2/*.json` (plan 3 creates them; the folder is passed or derived from `site.MEMORIES`).
- Produces: `holdout.write_outcome(memory: str, public: Path | None, out: Path | None = None) -> dict` writing `examples/<folder>_report/holdout.json` = `{"set": <manifest version>, "sha256": <manifest sha256>, "delta": 3.0, "outcome", "x", "y", "public_builds", "private_builds"}`, and returning it; `SystemExit("no public2 runs for <memory>")` when the public folder has none, writing nothing.

- [ ] **Step 1: Write the failing tests (append)**

```python
def test_write_outcome_publishes_only_the_outcome(home, tmp_path):
    _tiny_holdout(home)
    holdout.run("synthetic", builds=1, say=lambda m: None, roots=[])
    pub = tmp_path / "pub"
    pub.mkdir()
    for f in (home / "runs" / "synthetic").glob("*.json"):
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest tests/test_holdout.py -q -k write_outcome`
Expected: FAIL, `write_outcome` missing.

- [ ] **Step 3: Implement (append to `adebench/holdout.py`, before `main`)**

```python
def write_outcome(memory: str, public: Path | None, out: Path | None = None) -> dict:
    from adebench import site
    entry = next((m for m in site.MEMORIES if m["name"].lower() == memory.lower()), None)
    folder = ROOT / "examples" / (entry["folder"] if entry else f"{memory}_report")
    public = public or folder / "runs_public2"
    pub = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(public).glob("*.json"))]
    if not pub:
        raise SystemExit(f"no public2 runs for {memory} in {public}")
    priv = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((home() / "runs" / memory).glob("*.json"))]
    if not priv:
        raise SystemExit(f"no private runs for {memory}: run `python -m adebench.holdout run --memory {memory}`")
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    c = holdout_compare.compare(pub, priv)
    result = {"set": m["version"], "sha256": m["sha256"], "delta": c["delta"], "outcome": c["outcome"], "x": c["x"],
              "y": c["y"], "public_builds": c["public_builds"], "private_builds": c["private_builds"]}
    out = out or folder / "holdout.json"
    out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result
```

Remove the placeholder import line in `main`'s `compare` branch so it reads `write_outcome(a.memory, Path(a.public) if a.public else None)` and prints `f"{a.memory}: lower by {r['x']}"` or `f"{a.memory}: no drop detected (±{r['y']})"`.

- [ ] **Step 4: Run all tests**

Run: `python -m pytest -q`
Expected: all pass.

---

### Task 6: Make and freeze `holdout-v1`, and the rule

**Files:**
- Create (outside the repo): `C:/Users/simon/adebench_holdout/holdout-v1/`
- Create: `sets/holdout.json`
- Modify: `README.md` (one sentence under **Sets**: the private set's version and sha256, where it lives, what is published)
- Create (assistant memory, outside the repo): a memory file stating that no session opens `C:/Users/simon/adebench_holdout`, with an index line in `MEMORY.md`

**Interfaces:**
- Consumes: `holdout.make` (Task 1), CLI (Task 4).

- [ ] **Step 1: Generate (costs cents; run after the user's ok)**

Run: `python -m adebench.holdout make --version v1`
Expected: `attempt N: accepted; 24 questions, 12 abstention; sha256 …` then `holdout-v1 frozen, sha256 …`. Nothing else printed.

- [ ] **Step 2: Check it without reading it**

Run: `python -c "from adebench import holdout; print(holdout.frozen())"` → prints the folder path only.
Run: `python -m adebench.holdout run --memory synthetic --builds 1` → one line with a core score; no leak.

- [ ] **Step 3: Save the rule in the assistant's memory**

Write the memory file (type feedback): never open, read, list the contents of, or print anything from `C:/Users/simon/adebench_holdout`, in any session, including Brain work; only `python -m adebench.holdout` may touch it; **Why:** the private set is what makes the ADE Brain's rank credible; **How to apply:** agents running the holdout get the command and report only its printed lines.

- [ ] **Step 4: Run all tests; show files and message; commit after the user's ok**

Run: `python -m pytest -q` → all pass.

```
The private holdout: frozen outside the repo, run in isolation

adebench/holdout.py makes a private set outside every repository with
the same generator and validator as public2, keeps only its version and
sha256 in sets/holdout.json, and runs a memory on it with every output
captured privately, a fresh store deleted after each build, and a scan
for the set's canary everywhere it must not be. adebench/holdout_compare.py
tells whether a memory's core score drops on the private set: lower by X,
or no drop detected ±Y (one-sided, 90 % bootstrap interval over runs and
the set's own questions, delta 3).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
