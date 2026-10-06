"""One build of a memory on a set, from a fresh store; and the public runner.

    python -m adebench.builds --memory mem0 --set public2            # builds from the registry
    python -m adebench.builds --memory engram --set public2 --builds 1

A public run writes its reports to examples/<folder>/runs_public2/ (runs_gemini_public2 for the
Gemini row) and then summarises them with adebench.repeats. The private runner
(adebench.holdout.run) calls build_once too, with its own folders and environment.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import IO

from adebench import registry

ROOT = Path(__file__).resolve().parents[1]


class BuildFailed(Exception):
    """str(e) is the stage that failed: import, server or benchmark."""


def _python(args: list[str], env: dict, log: IO) -> int:
    return subprocess.call([sys.executable, *args], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)


def _env(entry: dict, store: Path, set_folder: Path, base_env: dict) -> dict:
    env = {**base_env, **{k: v.replace("{store}", str(store)) for k, v in entry.get("env", {}).items()},
           "ADEBENCH_SET": str(set_folder), "ADEBENCH_LIVE_STATE_KEY": "", "PYTHONIOENCODING": "utf-8"}
    if entry.get("store_env"):
        env[entry["store_env"]] = str(store)
    return env


def _up(url: str, wait_s: int, proc) -> bool:
    end = time.time() + wait_s
    while time.time() < end:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if 200 <= r.status < 300:
                    return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def _stop(proc) -> None:
    """Stop the server and everything it started: a launcher (npm, the agentmemory CLI) starts the
    real server as a child, which killing the launcher alone would leave running."""
    if os.name == "nt":
        subprocess.call(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif proc.poll() is None:
        os.killpg(proc.pid, signal.SIGKILL)
    proc.wait(timeout=30)


def _start(server: dict, store: Path, env: dict, log: IO):
    """Start the memory's server on the fresh store, wait until its health URL answers."""
    sub = lambda s: s.replace("{store}", str(store))  # noqa: E731
    proc = subprocess.Popen([sub(c) for c in server["cmd"]], cwd=sub(server.get("cwd") or "") or None,
                            env={**env, **{k: sub(v) for k, v in server.get("env", {}).items()}},
                            stdout=log, stderr=subprocess.STDOUT, start_new_session=os.name != "nt")
    if not _up(server["health"], server.get("wait_s", 60), proc):
        _stop(proc)
        raise BuildFailed("server")
    return proc


def build_once(entry: dict, set_folder: Path, store: Path, runs_dir: Path, log: IO, base_env: dict) -> Path:
    """Import the set into the memory's fresh `store` and run the benchmark; return the new report.
    A server entry is started first and always stopped. The caller creates and deletes `store`."""
    env = _env(entry, store, set_folder, base_env)
    before = set(runs_dir.glob("*.json"))
    for cmd in entry.get("prepare", []):   # e.g. gbrain init in the fresh store
        if subprocess.call([c.replace("{store}", str(store)) for c in cmd], cwd=store, env=env,
                           stdout=log, stderr=subprocess.STDOUT) != 0:
            raise BuildFailed("prepare")
    proc = _start(entry["server"], store, env, log) if entry.get("server") else None
    try:
        if entry.get("import") and _python([entry["import"]], env, log) != 0:
            raise BuildFailed("import")
        code = _python(["-m", "adebench", "--adapter", entry["adapter"], "--cases", str(set_folder / "cases"),
                        "--repo", str(set_folder / "repo"), "--history", str(runs_dir), *entry["flags"]], env, log)
    finally:
        if proc:
            _stop(proc)
    new = sorted(set(runs_dir.glob("*.json")) - before)
    if code != 0 or not new:
        raise BuildFailed("benchmark")
    return new[-1]


# ─── the public runner ───────────────────────────────────────────────────────

def cases_hash(set_folder: Path) -> str:
    """The hash a report records in config.cases_hash (adebench/report.py), for a set's folder."""
    h = hashlib.sha1()
    for name in ("questions.json", "abstention.json"):
        p = Path(set_folder) / "cases" / name
        if p.exists():
            h.update(name.encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:10]


def runs_dir_name(entry: dict, set_name: str) -> str:
    """runs / runs_gemini on quick (the folders the board has always used), runs_public2 /
    runs_gemini_public2 on public2."""
    suffix = entry.get("file", "reference")[len("reference"):]
    return "runs" + suffix + ("" if set_name == "quick" else f"_{set_name}")


def public(memory: str, set_name: str, n: int | None = None, out: Path | None = None, say=print) -> dict:
    """Run `memory` on the public set `set_name`, n builds (the registry's count by default),
    each from a fresh store, then summarise every run in the folder with adebench.repeats."""
    from adebench import repeats   # repeats imports site: not at the top
    e = registry.entry(memory)
    set_folder = ROOT / "sets" / set_name
    folder = Path(out) if out else ROOT / "examples" / e["folder"]
    runs = folder / runs_dir_name(e, set_name)
    runs.mkdir(parents=True, exist_ok=True)
    want = cases_hash(set_folder)
    for f in runs.glob("*.json"):
        got = (json.loads(f.read_text(encoding="utf-8")).get("config") or {}).get("cases_hash")
        if got != want:
            raise SystemExit(f"{f} is a run on another set ({got}, {set_name} is {want}): move it first")
    for b in range(1, (n or registry.builds_for(memory, private=False)) + 1):
        store = Path(tempfile.mkdtemp(prefix=f"adebench-{memory}-"))
        log_path = Path(tempfile.gettempdir()) / f"adebench-{memory}-{set_name}-{datetime.now():%Y%m%d-%H%M%S}-{b}.log"
        try:
            with open(log_path, "w", encoding="utf-8") as log:
                build_once(e, set_folder, store, runs, log, registry.clean_env())
        except BuildFailed as err:
            raise SystemExit(f"{memory} build {b}: {err} failed, log {log_path}")
        finally:
            shutil.rmtree(store, ignore_errors=True)
        say(f"{memory} {set_name} build {b} done")
    s = repeats.write(folder, runs.name)
    c = s["core"]
    say(f"{memory} {set_name}: {s['builds']} runs, core mean {c['mean']} ({c['min']}-{c['max']})")
    return s


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="adebench.builds", description="Run a memory on a public set, repeated builds.")
    ap.add_argument("--memory", required=True)
    ap.add_argument("--set", default="public2")
    ap.add_argument("--builds", type=int, help="default: 5 with a model inside, 3 without")
    ap.add_argument("--out", help="report folder (default examples/<folder>)")
    a = ap.parse_args(argv)
    public(a.memory, a.set, a.builds, Path(a.out) if a.out else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
