"""Sets as data: the loader gives the importers today's constants."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from adebench import sets

ROOT = Path(__file__).resolve().parents[1]

# today's constants, frozen here so the conversion cannot drift
OLD_CARD_DATES = {"brain": "2026-09-01", "mailbox": "2026-08-20", "calendar": "2026-08-30", "owner": "2026-09-05"}
OLD_FACT_KEYS = ["brain_port", "brain_model", "mailbox_version", "mailbox_tools", "calendar_refresh",
                 "owner_city", "owner_meetings", "travel_train", "travel_bike", "backup_policy"]


def test_quick_gives_todays_constants():
    c = sets.load(ROOT / "sets" / "quick").constants()
    assert c["CARD_DATES"] == OLD_CARD_DATES
    assert [f["key"] for f in c["FACTS"]] == OLD_FACT_KEYS
    assert c["FACTS"][2] == {"key": "mailbox_version", "content": "MailBridge 1.4.2 replaced 1.3.0 on 2026-08-20.",
                             "event_date": "2026-08-20", "entity": "mailbox", "attribute": "version"}
    assert c["FACTS"][7]["event_date"] is None
    assert c["EPISODES"][3] == {"created_at": "2026-09-08T08:30:00", "repl": "pc2:chat",
                                "input_summary": "[pc2] Sync the calendar cache", "output_summary": "Cache refreshed"}
    assert [a["alias"] for a in c["ALIASES"]] == ["the_brain", "mail_bridge", "agenda"]
    assert len(c["CORRECTIONS"]) == 2 and c["CARDS"]["owner"].startswith("The owner is Alex")


def test_synthetic_module_reads_the_same_data():
    from examples import synthetic
    c = sets.load(ROOT / "sets" / "quick").constants()
    assert synthetic.CARDS == c["CARDS"] and synthetic.FACTS == c["FACTS"] and synthetic.EPISODES == c["EPISODES"]


def test_current_reads_the_flag_then_the_env(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.argv", ["x"])
    monkeypatch.delenv("ADEBENCH_SET", raising=False)
    assert sets.current().name == "quick"
    other = tmp_path / "other"
    other.mkdir()
    (other / "world.json").write_text(json.dumps({"name": "other", "as_of": "2026-01-01", "cards": [],
                                                  "corrections": [], "aliases": [], "facts": [], "episodes": []}))
    monkeypatch.setenv("ADEBENCH_SET", str(other))
    assert sets.current().name == "other"
    monkeypatch.setattr("sys.argv", ["x", "--set", str(ROOT / "sets" / "quick")])
    assert sets.current().name == "quick"


def test_a_folder_without_world_json_names_the_path(tmp_path):
    with pytest.raises(SystemExit, match=re.escape(str(tmp_path))):
        sets.load(tmp_path)


def test_sha_changes_with_content(tmp_path):
    import shutil
    shutil.copytree(ROOT / "sets" / "quick", tmp_path / "q")
    before = sets.sha256(tmp_path / "q")
    w = json.loads((tmp_path / "q" / "world.json").read_text(encoding="utf-8"))
    w["facts"][0]["text"] += " "
    (tmp_path / "q" / "world.json").write_text(json.dumps(w), encoding="utf-8")
    assert sets.sha256(tmp_path / "q") != before


QUICK_CASES_HASH = "0f9a4640dc"   # the hash every published quick report was run with


def test_quick_cases_keep_their_hash(monkeypatch):
    from adebench import report
    from adebench.config import CFG
    monkeypatch.setattr(CFG, "cases", ROOT / "sets" / "quick" / "cases")
    assert report.cases_hash() == QUICK_CASES_HASH


def test_quick_set_json_matches_its_content():
    meta = json.loads((ROOT / "sets" / "quick" / "set.json").read_text(encoding="utf-8"))
    assert meta["sha256"] == sets.sha256(ROOT / "sets" / "quick")


def test_no_file_still_names_the_old_paths():
    old = ("examples/synthetic_data/cases", "examples/synthetic_data/repo")
    # published reports, specs and plans keep the paths they were written with
    frozen = {".git", "site", "scout", "specs", "superpowers", ".superpowers", ".pytest_cache"}
    skip = lambda p: bool(frozen & set(p.parts)) or any(part.endswith("_report") for part in p.parts)  # noqa: E731
    hits = [str(p) for p in ROOT.rglob("*") if p.suffix in (".py", ".md", ".yml") and not skip(p)
            and p.name != "test_sets.py" and any(o in p.read_text(encoding="utf-8", errors="ignore") for o in old)]
    assert hits == []


import importlib  # noqa: E402

IMPORTERS = ["ade", "agentmemory", "aionforge", "cognee", "dakera", "engram", "gbrain", "hindsight", "jevmem",
             "mem0", "memoose", "memu", "nemp", "supermemory", "tokenmizer"]


def test_no_importer_reads_the_constants_directly():
    hits = [n for n in IMPORTERS
            if "from examples.synthetic import" in (ROOT / "examples" / f"{n}_import.py").read_text(encoding="utf-8")]
    assert hits == []


@pytest.mark.parametrize("name", IMPORTERS)
def test_importer_takes_the_set_from_the_environment(name, tmp_path, monkeypatch):
    other = tmp_path / "tiny"
    other.mkdir()
    (other / "world.json").write_text(json.dumps({
        "name": "tiny", "as_of": "2026-01-02",
        "cards": [{"id": "card:x", "entity": "x", "text": "X is a test entity.", "date": "2026-01-01"}],
        "corrections": [], "aliases": [], "episodes": [],
        "facts": [{"id": "x_a", "entity": "x", "attribute": "a", "text": "X has A.", "date": None, "supersedes": None}]}))
    monkeypatch.setenv("ADEBENCH_SET", str(other))
    monkeypatch.setattr("sys.argv", ["x"])
    mod = importlib.reload(importlib.import_module(f"examples.{name}_import"))
    assert mod.CARDS == {"x": "X is a test entity."} and [f["key"] for f in mod.FACTS] == ["x_a"]


def test_public2_is_frozen_and_valid():
    from adebench import validate_set
    p = ROOT / "sets" / "public2"
    meta = json.loads((p / "set.json").read_text(encoding="utf-8"))
    assert meta["sha256"] == sets.sha256(p)
    w = json.loads((p / "world.json").read_text(encoding="utf-8"))
    qs = json.loads((p / "cases" / "questions.json").read_text(encoding="utf-8"))
    ab = json.loads((p / "cases" / "abstention.json").read_text(encoding="utf-8"))
    repo = {f.name: f.read_text(encoding="utf-8") for f in (p / "repo").glob("*.py")}
    problems = validate_set.check(w, qs, ab, repo, validate_set.MIX_PUBLIC)
    assert not any(problems.values()), {k: len(v) for k, v in problems.items() if v}


def test_fact_entity_prefers_the_worlds_entity_then_the_key():
    cards = {"brain": "", "owner": ""}
    assert sets.fact_entity({"key": "f1", "entity": "brain"}, cards) == "brain"
    assert sets.fact_entity({"key": "travel_train", "entity": "travel"}, cards, "owner") == "owner"
    assert sets.fact_entity({"key": "brain_port"}, cards) == "brain"


class _FakeGbrain:
    calls: list = []
    def health(self): return True
    def _call(self, name, payload): _FakeGbrain.calls.append((name, payload)); return {}


class _FakeMemoose:
    calls: list = []
    dataset = "t"
    def health(self): return True
    def _cli(self, args, stdin=None): _FakeMemoose.calls.append((args, stdin)); return {}
    def graph_counts(self): return {}


@pytest.mark.parametrize("name,fake,attr", [("gbrain", _FakeGbrain, "GbrainAdapter"),
                                            ("memoose", _FakeMemoose, "MemooseAdapter")])
def test_entity_aware_importers_build_on_a_generated_set(name, fake, attr, monkeypatch, capsys):
    monkeypatch.setenv("ADEBENCH_SET", str(ROOT / "sets" / "public2"))
    monkeypatch.setattr("sys.argv", ["x"])
    mod = importlib.reload(importlib.import_module(f"examples.{name}_import"))
    monkeypatch.setattr(mod, attr, fake)
    fake.calls = []
    assert mod.main() == 0 and len(fake.calls) > 40


def test_set_flag_with_equals_and_a_missing_value(monkeypatch, capsys):
    monkeypatch.delenv("ADEBENCH_SET", raising=False)
    monkeypatch.setattr("sys.argv", ["x", f"--set={ROOT / 'sets' / 'public2'}"])
    assert sets.current().name == "public2"
    assert "public2" in capsys.readouterr().err
    monkeypatch.setattr("sys.argv", ["x", "--set"])
    with pytest.raises(SystemExit, match="--set"):
        sets.current()
