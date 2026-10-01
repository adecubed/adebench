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


def test_dependency_trees_are_pruned(tmp_path):
    for d in ("node_modules", "__pycache__", ".git"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "f.txt").write_text("cnryabc123", encoding="utf-8")
    assert leaks.scan("cnryabc123", [tmp_path], exclude=[]) == []


def test_default_roots_cover_the_ade_folder_and_ollama_logs():
    names = {str(p).replace("\\", "/") for p in leaks.DEFAULT_ROOTS}
    assert "C:/Users/simon/ade" in names and any(n.endswith(".ollama/logs") for n in names)
