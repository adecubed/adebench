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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from adebench import genset, holdout_compare, leaks, sets, validate_set

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "sets" / "holdout.json"
MIX = validate_set.MIX_PUBLIC
# outside every repository: C:/Users/simon/ade is itself the orchestrator's repository
DEFAULT_HOME = Path("C:/Users/simon/adebench_holdout")
# variables of the parent shell that would change what is measured or where a memory writes
# (ADEBENCH_DOOR, ADEBENCH_PRESSURE, BRAIN_URL...): a private run starts without them and
# gets only what its registry entry sets
DROP_ENV = ("ADEBENCH_", "BRAIN_", "SUPERMEMORY_", "MEM0_", "COGNEE_", "MEMU_", "ENGRAM_", "AGENTMEMORY_",
            "DAKERA_", "HINDSIGHT_", "AIONFORGE_", "GBRAIN_", "MEMOOSE_", "JEVMEM_", "NEMP_")


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

# how to load and run each memory on the private set; plan 3 adds the real memories.
# store_env: the variable through which the memory takes its data folder (the runner
# points it at a fresh folder under <home>/stores and deletes it afterwards).
# cleanup: other folders the memory writes the set into (a server's data folder, its log),
# deleted after the run and scanned like the rest. A server memory must name its URL in env.
REGISTRY: dict[str, dict] = {
    "synthetic": {"adapter": "examples.synthetic:SyntheticAdapter", "import": None, "store_env": None,
                  "env": {}, "flags": ["--sections", "door", "updates", "time", "abstention", "--no-sandbox-test"]},
}


def _python(args: list[str], env: dict, log) -> int:
    return subprocess.call([sys.executable, *args], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)


def run(memory: str, builds: int = 1, say=print, roots: list[Path] | None = None) -> list[float]:
    """Run a memory on the frozen private set, `builds` times, each from a fresh store.
    Everything the memory and the benchmark print goes to the private folder; this
    prints one line per build with its core score. After every build the store is
    deleted and the canary is searched for outside the private folder."""
    entry = REGISTRY.get(memory)
    if entry is None:
        raise SystemExit(f"no registry entry for {memory!r}")
    folder = frozen()
    h = home()
    canary = json.loads((folder / "world.json").read_text(encoding="utf-8"))["canary"]
    runs_dir, logs, stores = h / "runs" / folder.name / memory, h / "logs", h / "stores"
    base_env = {k: v for k, v in os.environ.items() if not k.startswith(DROP_ENV)}
    for d in (runs_dir, logs, stores):
        d.mkdir(parents=True, exist_ok=True)
    scores = []
    for b in range(1, builds + 1):
        store = stores / f"{memory}-{b}"
        shutil.rmtree(store, ignore_errors=True)
        store.mkdir()
        env = {**base_env, **entry["env"], "ADEBENCH_SET": str(folder), "ADEBENCH_LIVE_STATE_KEY": "",
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
