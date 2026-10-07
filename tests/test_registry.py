"""Every board row that runs here has a registry entry that can run without the parent's settings."""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from adebench import builds, registry, site

ROOT = Path(__file__).resolve().parents[1]
HERE = {"engram", "memoose", "gbrain", "jevmem", "agentmemory", "agentmemory_gemini", "supermemory", "mem0",
        "cognee", "memu", "tokenmizer"}


def test_every_memory_run_here_has_an_entry_for_its_row():
    rows = {(m["folder"], m.get("file", "reference")) for m in site.MEMORIES}
    for name in HERE:
        e = registry.entry(name)
        assert (e["folder"], e["file"]) in rows, name


def test_entries_point_at_code_that_exists():
    for name in HERE:
        e = registry.entry(name)
        mod, cls = e["adapter"].split(":")
        assert hasattr(importlib.import_module(mod), cls), name
        assert e["import"] is None or (ROOT / e["import"]).exists(), name


def test_a_store_is_always_fresh_never_a_default_home():
    for name in HERE:
        e = registry.entry(name)
        server_env = (e.get("server") or {}).get("env", {})
        assert e["store_env"] or "{store}" in " ".join([*e["env"].values(), *server_env.values()]), name


def test_entry_without_its_home_fails_the_build(tmp_path):
    # mem0 without MEM0_HOME must not fall back to a default: the build fails at import
    e = registry.entry("mem0")
    e = dict(e, env={k: v for k, v in e["env"].items() if k != "MEM0_HOME"})
    (tmp_path / "runs").mkdir()
    (tmp_path / "store").mkdir()
    with open(tmp_path / "log.txt", "w", encoding="utf-8") as log, pytest.raises(builds.BuildFailed):
        builds.build_once(e, ROOT / "sets" / "quick", tmp_path / "store", tmp_path / "runs", log, registry.clean_env())


def test_tokenmizer_runs_on_its_own_config_with_the_key_from_the_environment():
    e = registry.entry("tokenmizer")
    assert (ROOT / "examples" / "tokenmizer.yaml").exists()
    assert e["server"]["env"]["TOKENMIZER_GEMINI_API_KEY"] == "{env:GEMINI_API_KEY}"
    assert "TOKENMIZER_" in registry.DROP_ENV
