"""The generator: validates, retries, writes, and never prints the content."""
from __future__ import annotations

import json

import pytest

from adebench import genset
from tests.test_validate_set import cases, world

SMALL_MIX = {"door": {"replaced": 1, "fact": 1, "never_stored": 1}, "abstention": 1}


def answer(w=None, qs=None, ab=None):
    q0, a0 = cases()
    return "```json\n" + json.dumps({"world": w or world(), "questions": qs or q0, "abstention": ab or a0,
                                     "repo": {"svc.py": "def start():\n    return 1\n"}}) + "\n```"


def test_a_valid_answer_is_written_with_its_hash(tmp_path):
    meta = genset.generate(tmp_path / "s", "s", 7, ask=lambda prompt: answer(), mix=SMALL_MIX, say=lambda m: None)
    assert (tmp_path / "s" / "world.json").exists() and (tmp_path / "s" / "cases" / "questions.json").exists()
    assert meta["attempts"] == 1 and meta["seed"] == 7 and len(meta["sha256"]) == 64


def test_an_invalid_answer_is_retried(tmp_path):
    bad = world()
    bad["aliases"].append({"alias": "zarvik", "canonical": "svc"})
    answers = iter([answer(w=bad), "not json at all", answer()])
    meta = genset.generate(tmp_path / "s", "s", 1, ask=lambda p: next(answers), mix=SMALL_MIX, say=lambda m: None)
    assert meta["attempts"] == 3


def test_five_failures_stop_and_write_nothing(tmp_path):
    with pytest.raises(SystemExit):
        genset.generate(tmp_path / "s", "s", 1, ask=lambda p: "{}", mix=SMALL_MIX, say=lambda m: None)
    assert not (tmp_path / "s").exists()


def test_nothing_of_the_content_is_printed(tmp_path):
    said = []
    genset.generate(tmp_path / "s", "s", 1, ask=lambda p: answer(), mix=SMALL_MIX, say=said.append)
    out = " ".join(said)
    for secret in ("9100", "Dana", "Zarvik", "Svc"):
        assert secret not in out


def test_parse_strips_a_fence_and_rejects_garbage():
    assert genset.parse(answer())["world"]["name"] == "t"
    with pytest.raises(ValueError):
        genset.parse("```json\n{broken\n```")


def test_an_existing_folder_is_never_overwritten(tmp_path):
    (tmp_path / "s").mkdir()
    with pytest.raises(SystemExit):
        genset.generate(tmp_path / "s", "s", 1, ask=lambda p: answer(), mix=SMALL_MIX, say=lambda m: None)
