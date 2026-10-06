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
import shutil
from datetime import datetime, timezone
from pathlib import Path

from adebench import builds as build_runner, genset, holdout_compare, leaks, registry, sets, validate_set

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "sets" / "holdout.json"
MIX = validate_set.MIX_PUBLIC
# outside every repository: C:/Users/simon/ade is itself the orchestrator's repository
DEFAULT_HOME = Path("C:/Users/simon/adebench_holdout")


def home() -> Path:
    return Path(os.environ.get("ADEBENCH_HOLDOUT") or DEFAULT_HOME)


def inside_a_repo(path: Path) -> bool:
    p = Path(path).resolve()
    return any((q / ".git").exists() for q in [p, *p.parents])


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
    """The private set the manifest names, after checking its sha256."""
    h = h or home()
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    folder = h / m["version"]
    if not (folder / "set.json").exists():
        local = sorted(p.name for p in h.glob("holdout-*")) if h.exists() else []
        raise SystemExit(f"the manifest names {m['version']}, the private folder has {local or 'nothing'}")
    got = sets.sha256(folder)
    if got != m["sha256"]:
        raise SystemExit(f"{m['version']}: sha256 {got[:12]} does not match the manifest's {m['sha256'][:12]}")
    return folder


# ─── the isolated runner ─────────────────────────────────────────────────────
# how each memory runs is in adebench/registry.py, shared with the public runs


def run(memory: str, builds: int = 1, say=print, roots: list[Path] | None = None) -> list[float]:
    """Run a memory on the frozen private set, `builds` times, each from a fresh store.
    Everything the memory and the benchmark print goes to the private folder; this
    prints one line per build with its core score. After every build the store is
    deleted and the canary is searched for outside the private folder."""
    entry = registry.entry(memory)
    folder = frozen()
    h = home()
    canary = json.loads((folder / "world.json").read_text(encoding="utf-8"))["canary"]
    runs_dir, logs, stores = h / "runs" / folder.name / memory, h / "logs", h / "stores"
    base_env = registry.clean_env()
    for d in (runs_dir, logs, stores):
        d.mkdir(parents=True, exist_ok=True)
    scores = []
    for b in range(1, builds + 1):
        store = stores / f"{memory}-{b}"
        shutil.rmtree(store, ignore_errors=True)
        store.mkdir()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            with open(logs / f"{memory}-{stamp}-{b}.log", "w", encoding="utf-8") as log:
                new = build_runner.build_once(entry, folder, store, runs_dir, log, base_env)
            report = json.loads(new.read_text(encoding="utf-8"))
            scores.append(round(holdout_compare.core55(holdout_compare.core_cases(report)), 1))
            say(f"{memory} build {b}: core {scores[-1]} / 55")
        except build_runner.BuildFailed as e:
            raise SystemExit(f"{memory} build {b}: {e} failed (log in the private folder)")
        finally:
            shutil.rmtree(store, ignore_errors=True)
            for extra in entry.get("cleanup", []):
                shutil.rmtree(extra, ignore_errors=True)
    # one scan per run, not per build: the stores are gone, anything left is a leak
    extra_roots = [Path(e).parent for e in entry.get("cleanup", [])]
    hits = leaks.scan(canary, (leaks.DEFAULT_ROOTS if roots is None else roots) + extra_roots, exclude=[h])
    if hits:
        raise SystemExit("private set leaked into: " + ", ".join(str(p) for p in hits))
    return scores


def write_outcome(memory: str, public: Path | None, out: Path | None = None) -> dict:
    """Compare the memory's public2 runs with its private runs and write the one
    thing published about the private set: examples/<memory>_report/holdout.json."""
    from adebench import site
    entry = next((m for m in site.MEMORIES if m["name"].lower() == memory.lower()), None)
    folder = ROOT / "examples" / (entry["folder"] if entry else f"{memory}_report")
    public = Path(public) if public else folder / "runs_public2"
    pub = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(public.glob("*.json"))]
    if not pub:
        raise SystemExit(f"no public2 runs for {memory} in {public}")
    version = frozen().name
    priv = [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted((home() / "runs" / version / memory).glob("*.json"))]
    if not priv:
        raise SystemExit(f"no private runs for {memory}: run `python -m adebench.holdout run --memory {memory}`")
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    c = holdout_compare.compare(pub, priv)
    result = {"set": m["version"], "sha256": m["sha256"], "delta": c["delta"], "outcome": c["outcome"], "x": c["x"],
              "y": c["y"], "public_builds": c["public_builds"], "private_builds": c["private_builds"]}
    out = out or folder / "holdout.json"
    out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="adebench.holdout", description="The private holdout set: make, run, compare.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make", help="generate and freeze a private set (prints only its hash)")
    mk.add_argument("--version", required=True)
    rn = sub.add_parser("run", help="run a memory on the private set (prints only core scores)")
    rn.add_argument("--memory", required=True)
    rn.add_argument("--builds", type=int, default=1)
    cp = sub.add_parser("compare", help="write the memory's holdout outcome")
    cp.add_argument("--memory", required=True)
    cp.add_argument("--public", help="folder of the memory's public2 runs (default examples/<memory>_report/runs_public2)")
    a = ap.parse_args(argv)
    if a.cmd == "make":
        m = make(a.version, genset.gemini("gemini-3-flash-preview"))
        print(f"{m['version']} frozen, sha256 {m['sha256'][:12]}")
    elif a.cmd == "run":
        run(a.memory, a.builds)
    else:
        r = write_outcome(a.memory, Path(a.public) if a.public else None)
        print(f"{a.memory}: lower by {r['x']}" if r["outcome"] == "lower" else
              f"{a.memory}: no drop detected (±{r['y']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
