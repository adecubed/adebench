"""One build from a fresh store, the same for public and private runs."""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

import pytest

from adebench import builds, registry

ROOT = Path(__file__).resolve().parents[1]


def _run(entry, tmp_path, env=None):
    runs = tmp_path / "runs"
    runs.mkdir(exist_ok=True)
    store = tmp_path / "store"
    store.mkdir(exist_ok=True)
    with open(tmp_path / "log.txt", "w", encoding="utf-8") as log:
        return builds.build_once(entry, ROOT / "sets" / "quick", store, runs, log, env or dict(os.environ))


def test_a_build_writes_one_report(tmp_path):
    report = _run(registry.entry("synthetic"), tmp_path)
    assert report.parent == tmp_path / "runs" and json.loads(report.read_text(encoding="utf-8"))["sections"]


def test_the_store_placeholder_reaches_the_memory(tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text("import os, sys\nsys.exit(0 if os.environ['X_STORE'].endswith('store') else 1)\n", encoding="utf-8")
    entry = dict(registry.entry("synthetic"), **{"import": str(probe), "env": {"X_STORE": "{store}"}})
    _run(entry, tmp_path)


def test_a_failing_import_names_its_stage(tmp_path):
    entry = dict(registry.entry("synthetic"), **{"import": "examples/does_not_exist.py"})
    with pytest.raises(builds.BuildFailed, match="import"):
        _run(entry, tmp_path)


def test_builds_per_side():
    assert registry.builds_for("synthetic", private=False) == 3 and registry.builds_for("synthetic", private=True) == 1


def _port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_a_server_runs_for_the_build_and_is_stopped(tmp_path):
    port = _port()
    probe = tmp_path / "probe.py"   # the import only passes if the server answers during the build
    probe.write_text(f"import urllib.request\nurllib.request.urlopen('http://127.0.0.1:{port}/', timeout=5)\n",
                     encoding="utf-8")
    entry = dict(registry.entry("synthetic"), **{"import": str(probe)}, server={
        "cmd": [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1", "--directory", "{store}"],
        "cwd": None, "env": {}, "health": f"http://127.0.0.1:{port}/", "wait_s": 20})
    _run(entry, tmp_path)
    time.sleep(0.5)
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1)


def test_server_that_never_answers_fails_and_is_killed(tmp_path):
    port = _port()
    entry = dict(registry.entry("synthetic"), server={
        "cmd": [sys.executable, "-c", "import time; time.sleep(60)"], "cwd": None, "env": {},
        "health": f"http://127.0.0.1:{port}/", "wait_s": 2})
    t = time.time()
    with pytest.raises(builds.BuildFailed, match="server"):
        _run(entry, tmp_path)
    assert time.time() - t < 20


def test_runs_dir_names():
    e = registry.entry("synthetic")
    assert builds.runs_dir_name(e, "public2") == "runs_public2" and builds.runs_dir_name(e, "quick") == "runs"
    assert builds.runs_dir_name(dict(e, file="reference_gemini"), "public2") == "runs_gemini_public2"


def test_cases_hash_matches_the_reports():
    assert builds.cases_hash(ROOT / "sets" / "quick") == "0f9a4640dc"


def test_public_writes_runs_and_the_summary(tmp_path):
    s = builds.public("synthetic", "quick", n=2, out=tmp_path, say=lambda m: None)
    assert s["builds"] == 2 and (tmp_path / "repeats.json").exists() and (tmp_path / "reference.json").exists()


def test_runs_from_another_set_are_refused(tmp_path):
    builds.public("synthetic", "quick", n=1, out=tmp_path, say=lambda m: None)
    (tmp_path / "runs" / "x.json").write_text('{"config": {"cases_hash": "other"}, "sections": []}', encoding="utf-8")
    with pytest.raises(SystemExit, match="another set"):
        builds.public("synthetic", "quick", n=1, out=tmp_path, say=lambda m: None)


def test_a_launcher_server_is_stopped_with_its_children(tmp_path):
    # the server command starts the real server as a child (npm, the agentmemory CLI do this)
    port = _port()
    launcher = tmp_path / "launcher.py"
    launcher.write_text(
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-m', 'http.server', '{port}', '--bind', '127.0.0.1'])\n"
        "time.sleep(600)\n", encoding="utf-8")
    entry = dict(registry.entry("synthetic"), server={
        "cmd": [sys.executable, str(launcher)], "cwd": None, "env": {},
        "health": f"http://127.0.0.1:{port}/", "wait_s": 20})
    _run(entry, tmp_path)
    time.sleep(1)
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1)


def test_prepare_commands_run_in_the_store_before_the_import(tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text("import os, sys\nsys.exit(0 if os.path.exists(os.path.join(os.environ['X_STORE'], 'ready')) else 1)\n",
                     encoding="utf-8")
    entry = dict(registry.entry("synthetic"), **{"import": str(probe), "env": {"X_STORE": "{store}"},
                                                  "prepare": [[sys.executable, "-c", "open('ready', 'w')"]]})
    _run(entry, tmp_path)


def test_a_failing_prepare_names_its_stage(tmp_path):
    entry = dict(registry.entry("synthetic"), prepare=[[sys.executable, "-c", "raise SystemExit(3)"]])
    with pytest.raises(builds.BuildFailed, match="prepare"):
        _run(entry, tmp_path)
