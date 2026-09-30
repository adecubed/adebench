# Sets as data, generator, validator and public2 — Implementation Plan (1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the synthetic set into a data folder every importer reads through `--set`, add a Gemini set generator and a mechanical validator, and produce the frozen public set `public2`.

**Architecture:** A set is a folder `sets/<name>/` (`world.json`, `cases/`, `repo/`, `set.json`). `adebench/sets.py` loads it and exposes the same constants the importers use today (`CARDS`, `CARD_DATES`, `FACTS`, `ALIASES`, `EPISODES`, `CORRECTIONS`), so each importer changes one import line. `adebench/validate_set.py` checks a set against its own world, rule by rule. `adebench/genset.py` asks Gemini for a set from a fixed mix, validates it, retries, and writes it without printing its content.

**Tech Stack:** Python 3.11, standard library only (urllib for Gemini), pytest.

**Spec:** `docs/specs/2026-09-30-sets-and-holdout-design.md` (sections 1, 2, 3 and the order of work 1-3). Plan 2 covers the holdout (section 4-5), plan 3 the runs and the site (section 6).

## Global Constraints

- Zero third-party dependencies in `adebench/` (pyproject `dependencies = []`).
- Everything public is in English (README, docs, code, sets).
- Never commit or push without the user's explicit ok: at every "Commit" step, show the files and the full message and wait.
- The `quick` set keeps its content: `report.cases_hash()` on `sets/quick/cases` must equal today's hash on `examples/synthetic_data/cases`, and `examples/synthetic_report/reference.json` must not move.
- A generated set is never edited by hand. A failing set is discarded and regenerated (at most 5 attempts).
- The generator never prints a set's content: only counts and pass/fail per rule.
- The key comes from `GOOGLE_API_KEY`, read in code; never on a command line, never in a file or log.
- `public2` mix: 24 door questions (8 plain facts, 4 carried by a card, 3 through an alias, 3 on a replaced value with `forbidden`, 3 dated, 3 never stored), 12 abstention questions (3 of them naming a real entity next to the invented one), history of 8 cards, 30 facts (at least 4 undated, 3 replaced pairs), 6 aliases, 3 corrections ("In the X card never omit: ..."), 12 episodes (3 signed `[pc2]`), a repo of 3 Python files with at least 12 functions in all.

## Review Focus

- A world whose `as_of` is before some fact dates: facts after `as_of` must not count as evidence (tested in Task 4).
- An alias that normalises to an invented entity ("Girandola" vs "girandola_notturna"): must fail the abstention rule (Task 4).
- A never-stored answer that appears only inside the repo files: must fail (Task 4).
- Gemini returning JSON wrapped in a markdown fence, or with a trailing comment: the parser must strip the fence and fail cleanly on invalid JSON, counting an attempt, not crash (Task 5).
- Running an importer with `--set` pointing at a folder with no `world.json`: a clear error naming the path, before touching the memory (Task 3).

---

### Task 1: The set loader, and `quick` as data

**Files:**
- Create: `adebench/sets.py`
- Create: `sets/quick/world.json`, `sets/quick/set.json`
- Create: `tests/test_sets.py`
- Modify: `examples/synthetic.py:32-77` (constants now come from the loader)

**Interfaces:**
- Produces: `sets.load(path: str | Path) -> World`; `World` is a dataclass with `name: str`, `as_of: str`, `cards: list[dict]` (`id`, `entity`, `text`, `date`), `corrections: list[dict]`, `aliases: list[dict]`, `facts: list[dict]` (`id`, `entity`, `attribute`, `text`, `date` or None, `supersedes` or None), `episodes: list[dict]` (`id`, `created_at`, `repl`, `input`, `output`), `canary: str | None`, `path: Path`. Method `World.constants() -> dict` returning `CARDS`, `CARD_DATES`, `CORRECTIONS`, `ALIASES`, `FACTS`, `EPISODES` in today's shapes (FACTS items `{"key","content","event_date"}`, EPISODES items `{"created_at","repl","input_summary","output_summary"}`). `sets.current() -> World` reads `--set <path>` from `sys.argv` or `ADEBENCH_SET`, default `sets/quick`. `sets.sha256(path) -> str` over the canonical content.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sets.py
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
                             "event_date": "2026-08-20"}
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sets.py -q`
Expected: FAIL, `ImportError: cannot import name 'sets'`.

- [ ] **Step 3: Write the loader**

```python
# adebench/sets.py
"""A golden set as data: sets/<name>/{world.json, cases/, repo/, set.json}.

The world is the history a memory is loaded with; cases are the questions;
repo is the small repository for file search. Importers read the world
through current(), so `--set <folder>` (or ADEBENCH_SET) picks the set and
the default is sets/quick, the original synthetic set.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "sets" / "quick"


@dataclass
class World:
    name: str
    as_of: str
    cards: list[dict] = field(default_factory=list)
    corrections: list[dict] = field(default_factory=list)
    aliases: list[dict] = field(default_factory=list)
    facts: list[dict] = field(default_factory=list)
    episodes: list[dict] = field(default_factory=list)
    canary: str | None = None
    path: Path = DEFAULT

    def constants(self) -> dict:
        """The shapes the importers and examples/synthetic.py have always used."""
        return {
            "CARDS": {c["entity"]: c["text"] for c in self.cards},
            "CARD_DATES": {c["entity"]: c["date"] for c in self.cards},
            "CORRECTIONS": [dict(c) for c in self.corrections],
            "ALIASES": [dict(a) for a in self.aliases],
            "FACTS": [{"key": f["id"], "content": f["text"], "event_date": f.get("date")} for f in self.facts],
            "EPISODES": [{"created_at": e["created_at"], "repl": e["repl"], "input_summary": e["input"],
                          "output_summary": e["output"]} for e in self.episodes],
        }


def load(path: str | Path) -> World:
    path = Path(path)
    f = path / "world.json"
    if not f.is_file():
        raise SystemExit(f"no world.json in {path}: not a set folder")
    w = json.loads(f.read_text(encoding="utf-8"))
    keys = ("cards", "corrections", "aliases", "facts", "episodes")
    return World(name=w["name"], as_of=w["as_of"], canary=w.get("canary"), path=path,
                 **{k: w.get(k, []) for k in keys})


def current() -> World:
    argv = sys.argv
    if "--set" in argv and argv.index("--set") + 1 < len(argv):
        return load(argv[argv.index("--set") + 1])
    return load(os.environ.get("ADEBENCH_SET") or DEFAULT)


def sha256(path: str | Path) -> str:
    """Hash of a set's content (world, cases, repo), independent of set.json and
    of line endings, so the same set hashes the same on every machine."""
    path = Path(path)
    h = hashlib.sha256()
    files = [path / "world.json"] + sorted((path / "cases").glob("*.json")) + sorted((path / "repo").rglob("*.py"))
    for p in files:
        if p.is_file():
            h.update(p.relative_to(path).as_posix().encode())
            h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()
```

- [ ] **Step 4: Write `sets/quick/world.json` from today's constants**

Run this once (it reads the constants still in `examples/synthetic.py` before Step 5 changes it):

```bash
python - <<'EOF'
import json
from pathlib import Path
import examples.synthetic as s
facts = []
for f in s.FACTS:
    entity, _, attribute = f["key"].partition("_")
    facts.append({"id": f["key"], "entity": entity, "attribute": attribute, "text": f["content"],
                  "date": f["event_date"], "supersedes": None})
world = {"name": "quick", "as_of": "2026-09-11",
         "cards": [{"id": f"card:{e}", "entity": e, "text": t, "date": s.CARD_DATES[e]} for e, t in s.CARDS.items()],
         "corrections": s.CORRECTIONS, "aliases": s.ALIASES, "facts": facts,
         "episodes": [{"id": f"ep{i+1}", "created_at": e["created_at"], "repl": e["repl"],
                       "input": e["input_summary"], "output": e["output_summary"]} for i, e in enumerate(s.EPISODES)],
         "canary": None}
out = Path("sets/quick"); out.mkdir(parents=True, exist_ok=True)
(out / "world.json").write_text(json.dumps(world, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
EOF
```

- [ ] **Step 5: Make `examples/synthetic.py` read the loader**

Replace the literal `CARDS`, `CARD_DATES`, `CORRECTIONS`, `ALIASES`, `FACTS`, `EPISODES` blocks (lines 34-77) with:

```python
from adebench import sets as _sets

_C = _sets.load(_sets.DEFAULT).constants()
CARDS, CARD_DATES, CORRECTIONS = _C["CARDS"], _C["CARD_DATES"], _C["CORRECTIONS"]
ALIASES, FACTS, EPISODES = _C["ALIASES"], _C["FACTS"], _C["EPISODES"]
```

Keep `GRAPH_EDGES` and `FACT_NODES` (they are the synthetic memory's own behaviour, not the set) and the docstring's list of deliberate defects.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest -q`
Expected: all pass, including `tests/test_adebench.py`'s synthetic reference test (the report does not move).

- [ ] **Step 7: Commit (after the user's ok)**

Show `adebench/sets.py`, `sets/quick/world.json`, `examples/synthetic.py`, `tests/test_sets.py` and the message:

```
Load the synthetic set from sets/quick/world.json

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 2: Move the quick cases and repo into the set folder

**Files:**
- Move: `examples/synthetic_data/cases/` → `sets/quick/cases/`, `examples/synthetic_data/repo/` → `sets/quick/repo/` (`git mv`)
- Create: `sets/quick/set.json`
- Modify: every file that names `examples/synthetic_data/cases` or `examples/synthetic_data/repo`: `.github/workflows/test.yml`, `tests/test_adebench.py` (lines 712-714, 850, 896), `examples/dakera_import.py:92`, the docstrings of `adebench/{agentmemory,aionforge,cognee,dakera,engram,hindsight,jevmem,mem0,memu,nemp,supermemory,tokenmizer}.py` and `examples/*_import.py`, `README.md`, `docs/memories.md` (its commands must keep working)
- Do not touch: published reports (`examples/*_report/`), specs and plans (`docs/specs/`, `docs/superpowers/`): they record the paths as they were
- Keep: `examples/synthetic_data/sandbox_test.py` and `census.json` (they belong to the synthetic memory, not to the set)
- Test: `tests/test_sets.py`

**Interfaces:**
- Consumes: `sets.sha256`, `sets.load` (Task 1).
- Produces: `sets/quick/set.json` = `{"name": "quick", "version": "1", "written_by": "hand, 2026-09-11", "sha256": <sets.sha256>, "cases_hash": <report.cases_hash() of sets/quick/cases>}`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_sets.py
QUICK_CASES_HASH = None  # filled in Step 2 from the current folder, then frozen


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
    frozen = {".git", "site", "scout", "specs", "superpowers"}
    skip = lambda p: bool(frozen & set(p.parts)) or any(part.endswith("_report") for part in p.parts)  # noqa: E731
    hits = [str(p) for p in ROOT.rglob("*") if p.suffix in (".py", ".md", ".yml") and not skip(p)
            and any(o in p.read_text(encoding="utf-8", errors="ignore") for o in old)]
    assert hits == []
```

- [ ] **Step 2: Freeze today's cases hash**

Run: `python -c "from adebench import report; from adebench.config import CFG; from pathlib import Path; CFG.cases = Path('examples/synthetic_data/cases'); print(report.cases_hash())"`
Put the printed value in `QUICK_CASES_HASH` in the test (a string literal).

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python -m pytest tests/test_sets.py -q`
Expected: FAIL (the folder does not exist yet; `set.json` missing; old paths found).

- [ ] **Step 4: Move and rewrite the paths**

```bash
git mv examples/synthetic_data/cases sets/quick/cases
git mv examples/synthetic_data/repo sets/quick/repo
grep -rl "examples/synthetic_data/cases\|examples/synthetic_data/repo" --include=*.py --include=*.md --include=*.yml . \
  | grep -v "^./site/\|_report/\|^./docs/specs/\|^./docs/superpowers/\|^./scout/" | xargs sed -i 's#examples/synthetic_data/cases#sets/quick/cases#g; s#examples/synthetic_data/repo#sets/quick/repo#g'
```

In `examples/dakera_import.py` replace `Path(__file__).resolve().parents[1] / "examples" / "synthetic_data" / "repo"` with `Path(__file__).resolve().parents[1] / "sets" / "quick" / "repo"`. In `tests/test_adebench.py` replace `root / "examples" / "synthetic_data" / "cases"` with `root / "sets" / "quick" / "cases"` (two places).

- [ ] **Step 5: Write `sets/quick/set.json`**

```bash
python -c "
import json; from pathlib import Path; from adebench import sets, report; from adebench.config import CFG
p = Path('sets/quick'); CFG.cases = p / 'cases'
meta = {'name': 'quick', 'version': '1', 'written_by': 'hand, 2026-09-11', 'sha256': sets.sha256(p), 'cases_hash': report.cases_hash()}
(p / 'set.json').write_text(json.dumps(meta, indent=1) + '\n', encoding='utf-8')"
```

- [ ] **Step 6: Run everything, including the CI command**

Run: `python -m pytest -q`, then the command in `.github/workflows/test.yml` locally.
Expected: all pass; the synthetic run prints `90.0 / 100` as `examples/synthetic_report/reference.json`.

- [ ] **Step 7: Commit (after the user's ok)**

```
Move the quick set's cases and repo into sets/quick

Same content and the same cases hash: every published report still
refers to the same set.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 3: Every importer takes `--set`

**Files:**
- Modify: `examples/{ade,agentmemory,aionforge,cognee,dakera,engram,gbrain,hindsight,jevmem,mem0,memoose,memu,nemp,supermemory,tokenmizer}_import.py` (the `from examples.synthetic import ...` line)
- Modify: `examples/dakera_import.py` (repo path: the set's `repo/`)
- Test: `tests/test_sets.py`

**Interfaces:**
- Consumes: `sets.current()`, `World.constants()` (Task 1).
- Produces: each importer module exposes the module-level names it used before (`CARDS`, `CARD_DATES`, `FACTS`, `ALIASES`, `EPISODES`), bound from the chosen set at import time.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_sets.py
import importlib

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
```

Note for the implementer: importing an importer must not contact its memory. If a module does work at import time, move that work into `main()` first.

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_sets.py -q -k importer`
Expected: FAIL on every importer.

- [ ] **Step 3: Replace the import line in each importer**

In each of the 15 files, replace the `from examples.synthetic import ...  # noqa: E402` line with:

```python
from adebench import sets  # noqa: E402

_C = sets.current().constants()
CARDS, CARD_DATES, FACTS, ALIASES, EPISODES = _C["CARDS"], _C["CARD_DATES"], _C["FACTS"], _C["ALIASES"], _C["EPISODES"]
```

and add to each module docstring's usage line: `--set sets/public2` (or `ADEBENCH_SET`) to load another set; the default is `sets/quick`. In `examples/dakera_import.py`, the repo path becomes `sets.current().path / "repo"`.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit (after the user's ok)**

```
Every importer loads the set named by --set

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 4: The set validator

**Files:**
- Create: `adebench/validate_set.py`
- Create: `tests/test_validate_set.py`

**Interfaces:**
- Consumes: `sets.World` (Task 1).
- Produces: `validate_set.check(world: dict, questions: list[dict], abstention: list, repo: dict[str, str], mix: dict | None) -> dict[str, list[str]]`, a map rule name → list of problems (empty lists when the rule passes); rule names `answerable`, `retired`, `never_stored`, `invented`, `leading`, `structure`. `validate_set.MIX_PUBLIC` holds the Global Constraints' mix. `validate_set.norm(text) -> str`, `validate_set.has_token(token, text) -> bool`.

Question format for generated sets (`questions.json`): the fields adebench reads today (`question`, `expected`, `forbidden`, `entity`, `validated`) plus `kind` (`fact`, `card`, `alias`, `replaced`, `dated`, `never_stored`) and `evidence` (list of world item ids). Abstention entries: `{"question": ..., "entity": ...}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_validate_set.py
"""The validator rejects a set for each rule it breaks (spec section 3)."""
from __future__ import annotations

import copy

from adebench import validate_set as v


def world():
    return {"name": "t", "as_of": "2026-06-30",
            "cards": [{"id": "card:svc", "entity": "svc", "text": "The Svc service listens on port 9100.", "date": "2026-06-01"}],
            "corrections": [], "aliases": [{"alias": "the_svc", "canonical": "svc"}],
            "facts": [{"id": "svc_port_old", "entity": "svc", "attribute": "port", "text": "Svc listens on port 9000.",
                       "date": "2026-02-01", "supersedes": None},
                      {"id": "svc_port", "entity": "svc", "attribute": "port", "text": "Svc moved from 9000 to 9100.",
                       "date": "2026-06-01", "supersedes": "svc_port_old"},
                      {"id": "svc_owner", "entity": "svc", "attribute": "owner", "text": "Svc is run by Dana.",
                       "date": "2026-03-01", "supersedes": None},
                      {"id": "svc_future", "entity": "svc", "attribute": "region", "text": "Svc runs in Oslo.",
                       "date": "2026-08-01", "supersedes": None}],
            "episodes": [{"id": "ep1", "created_at": "2026-06-02T10:00:00", "repl": "chat",
                          "input": "Check the Svc port", "output": "Port 9100 confirmed"}]}


def cases():
    qs = [{"question": "Which port does Svc use?", "expected": [["9100"]], "forbidden": [["9000"]],
           "kind": "replaced", "evidence": ["svc_port"]},
          {"question": "Who runs the service?", "expected": [["Dana"]], "kind": "fact", "evidence": ["svc_owner"]},
          {"question": "What is the owner's phone number?", "expected": [["+47"]], "kind": "never_stored", "evidence": []}]
    ab = [{"question": "What does the Zarvik module do?", "entity": "Zarvik"}]
    return qs, ab


def run(w=None, qs=None, ab=None, repo=None):
    q0, a0 = cases()
    return v.check(w or world(), qs if qs is not None else q0, ab if ab is not None else a0, repo or {}, None)


def test_a_good_set_passes():
    assert all(not p for p in run().values()), run()


def test_evidence_must_contain_the_answer():
    qs, _ = cases()
    qs[1]["evidence"] = ["svc_port"]
    assert run(qs=qs)["answerable"]


def test_superseded_evidence_fails():
    qs, _ = cases()
    qs[0]["evidence"] = ["svc_port_old"]
    qs[0]["expected"] = [["9000"]]
    qs[0]["forbidden"] = []
    assert run(qs=qs)["answerable"]


def test_evidence_after_as_of_fails():
    qs, _ = cases()
    qs.append({"question": "Where does Svc run?", "expected": [["Oslo"]], "kind": "fact", "evidence": ["svc_future"]})
    assert run(qs=qs)["answerable"]


def test_retired_value_as_a_current_fact_fails():
    w = world()
    w["facts"].append({"id": "svc_note", "entity": "svc", "attribute": "note", "text": "Clients connect on 9000.",
                       "date": "2026-06-10", "supersedes": None})
    assert run(w=w)["retired"]


def test_never_stored_answer_present_anywhere_fails():
    assert run(repo={"svc.py": "PHONE = '+47 555'\n"})["never_stored"]


def test_invented_entity_present_or_aliased_fails():
    w = world()
    w["aliases"].append({"alias": "zarvik", "canonical": "svc"})
    assert run(w=w)["invented"]
    w2 = world()
    w2["facts"][2]["text"] = "Svc is run by Dana from the Zarvik team."
    assert run(w=w2)["invented"]


def test_leading_question_fails():
    qs, _ = cases()
    qs[1]["question"] = "Is the service run by Dana?"
    assert run(qs=qs)["leading"]


def test_structure_mix_ids_dates_aliases():
    w = world()
    w["facts"][1]["id"] = "svc_port_old"
    assert run(w=w)["structure"]
    w = world()
    w["aliases"].append({"alias": "x", "canonical": "nobody"})
    assert run(w=w)["structure"]
    w = world()
    w["facts"][0]["date"] = "2026-13-45"
    assert run(w=w)["structure"]
    qs, ab = cases()
    assert v.check(world(), qs, ab, {}, {"door": {"fact": 2}, "abstention": 1})["structure"]


def test_normalisation_ignores_case_accents_and_punctuation():
    assert v.has_token("Brambillesco", "a note on brambillèsco, today")
    assert not v.has_token("9000", "port 19000")
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_validate_set.py -q`
Expected: FAIL, module not found.

- [ ] **Step 3: Implement the validator**

```python
# adebench/validate_set.py
"""Check a generated set against its own world (spec section 3).

Presence of text is not evidence: an answer counts only if an item the
question cites contains it, is dated on or before the set's as_of (or is
undated), and has not been superseded. Everything else that must be absent
is checked after normalising case, accents and punctuation.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

MIX_PUBLIC = {"door": {"fact": 8, "card": 4, "alias": 3, "replaced": 3, "dated": 3, "never_stored": 3},
              "abstention": 12, "cards": 8, "facts": 30, "aliases": 6, "corrections": 3, "episodes": 12}
RULES = ("answerable", "retired", "never_stored", "invented", "leading", "structure")


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    words = (w.strip(".") for w in re.sub(r"[^a-z0-9+.]+", " ", t).split())   # "9100." is the token 9100
    return " " + " ".join(w for w in words if w) + " "


def has_token(token: str, text: str) -> bool:
    return norm(token).strip() != "" and norm(token) in norm(text)


def _items(world: dict) -> dict[str, dict]:
    out = {}
    for c in world.get("cards", []):
        out[c["id"]] = {"text": c["text"], "date": c.get("date"), "entity": c["entity"], "attribute": "card"}
    for f in world.get("facts", []):
        out[f["id"]] = {"text": f["text"], "date": f.get("date"), "entity": f["entity"], "attribute": f["attribute"],
                        "supersedes": f.get("supersedes")}
    for e in world.get("episodes", []):
        out[e["id"]] = {"text": f"{e['input']} {e['output']}", "date": e["created_at"][:10], "entity": None,
                        "attribute": "episode"}
    return out


def _superseded(world: dict) -> set[str]:
    facts = world.get("facts", [])
    gone = {f["supersedes"] for f in facts if f.get("supersedes")}
    for f in facts:
        for g in facts:
            if (g is not f and g["entity"] == f["entity"] and g["attribute"] == f["attribute"]
                    and f.get("date") and g.get("date") and g["date"] > f["date"] and g["date"] <= world["as_of"]):
                gone.add(f["id"])
    return gone


def _valid_date(d) -> bool:
    try:
        date.fromisoformat(str(d)[:10])
        return True
    except ValueError:
        return False


def check(world: dict, questions: list[dict], abstention: list, repo: dict[str, str], mix: dict | None) -> dict:
    p = {r: [] for r in RULES}
    items, gone, as_of = _items(world), _superseded(world), world["as_of"]
    alias_text = " ".join(f"{a['alias'].replace('_', ' ')} {a['canonical']}" for a in world.get("aliases", []))
    everything = " ".join(i["text"] for i in items.values()) + " " + alias_text + " " + " ".join(repo.values())

    for q in questions:
        alts = [a for g in q.get("expected", []) for a in g]
        if any(has_token(a, q["question"]) for a in alts):
            p["leading"].append(q["question"])
        if q.get("kind") == "never_stored":
            if any(has_token(a, everything) for a in alts):
                p["never_stored"].append(q["question"])
            continue
        for group in q.get("expected", []):
            ok = False
            for eid in q.get("evidence", []):
                it = items.get(eid)
                if it is None or eid in gone or (it["date"] and it["date"][:10] > as_of):
                    continue
                if any(has_token(a, it["text"]) for a in group):
                    ok = True
            if not ok:
                p["answerable"].append(f"{q['question']} -> {group}")
        for group in q.get("forbidden", []):
            for eid, it in items.items():
                if any(has_token(a, it["text"]) for a in group) and eid not in gone \
                        and not any(has_token(a, it["text"]) for a in alts):
                    p["retired"].append(f"{q['question']} -> {eid}")

    real = {norm(c["entity"]) for c in world.get("cards", [])}
    for a in abstention:
        ent = a["entity"] if isinstance(a, dict) else None
        if not ent:
            p["structure"].append(f"abstention without entity: {a}")
            continue
        words = [w for w in norm(ent).split() if len(w) >= 5] or norm(ent).split()
        if any(has_token(w, everything) for w in words) or any(norm(al["alias"].replace("_", " ")) == norm(ent)
                                                               for al in world.get("aliases", [])):
            p["invented"].append(ent)
        if norm(ent) in real:
            p["invented"].append(f"{ent} is a real entity")

    ids = [c["id"] for c in world.get("cards", [])] + [f["id"] for f in world.get("facts", [])] \
        + [e["id"] for e in world.get("episodes", [])]
    if len(ids) != len(set(ids)):
        p["structure"].append("duplicate ids")
    for it in items.values():
        if it["date"] and not _valid_date(it["date"]):
            p["structure"].append(f"bad date {it['date']}")
    entities = {c["entity"] for c in world.get("cards", [])} | {f["entity"] for f in world.get("facts", [])}
    for al in world.get("aliases", []):
        if al["canonical"] not in entities:
            p["structure"].append(f"alias {al['alias']} -> unknown {al['canonical']}")
    if mix:
        kinds = {}
        for q in questions:
            kinds[q.get("kind")] = kinds.get(q.get("kind"), 0) + 1
        for k, n in mix.get("door", {}).items():
            if kinds.get(k, 0) != n:
                p["structure"].append(f"{k}: {kinds.get(k, 0)} questions, want {n}")
        if "abstention" in mix and len(abstention) != mix["abstention"]:
            p["structure"].append(f"abstention: {len(abstention)}, want {mix['abstention']}")
        for key in ("cards", "aliases", "corrections", "episodes"):
            if key in mix and len(world.get(key, [])) != mix[key]:
                p["structure"].append(f"{key}: {len(world.get(key, []))}, want {mix[key]}")
        if "facts" in mix and len(world.get("facts", [])) < mix["facts"]:
            p["structure"].append(f"facts: {len(world.get('facts', []))}, want at least {mix['facts']}")
    return p
```

- [ ] **Step 4: Run the tests and fix until green**

Run: `python -m pytest tests/test_validate_set.py -q`
Expected: PASS (all 11).

- [ ] **Step 5: Commit (after the user's ok)**

```
A validator for generated sets: evidence, not presence of text

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 5: The generator

**Files:**
- Create: `adebench/genset.py`
- Create: `tests/test_genset.py`

**Interfaces:**
- Consumes: `validate_set.check`, `validate_set.MIX_PUBLIC` (Task 4); `sets.sha256` (Task 1).
- Produces: `genset.generate(out: Path, name: str, seed: int, ask: Callable[[str], str], mix: dict = MIX_PUBLIC, attempts: int = 5, say: Callable[[str], None] = print) -> dict` (the `set.json` content); `genset.parse(text: str) -> dict` with keys `world`, `questions`, `abstention`, `repo`; `genset.gemini(model: str) -> Callable[[str], str]`; CLI `python -m adebench.genset --name public2 --seed N --out sets/public2 [--model gemini-3-flash-preview] [--canary]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_genset.py
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_genset.py -q`
Expected: FAIL, module not found.

- [ ] **Step 3: Implement the generator**

```python
# adebench/genset.py
"""Generate a golden set with a model, validate it, write it (spec section 2).

    python -m adebench.genset --name public2 --seed 11 --out sets/public2

The model gets a fixed specification (the mix in validate_set.MIX_PUBLIC),
returns world, questions, abstention and repo as one JSON document, and the
set is written only if every validator rule passes; otherwise it is thrown
away and asked again, at most five times. Nothing of the content is printed:
only the attempt count and, per failed attempt, how many problems each rule
found. The key is GOOGLE_API_KEY, read here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from adebench import sets, validate_set

SPEC = """You write a synthetic history for testing an AI assistant's memory, and questions about it.
Return ONE JSON object, nothing else, with keys "world", "questions", "abstention", "repo".
world: {{"name": "{name}", "as_of": "<YYYY-MM-DD>", "cards": [...], "corrections": [...], "aliases": [...],
  "facts": [...], "episodes": [...]}}
- cards: {cards} entities (people, services, projects, devices), each {{"id": "card:<entity>", "entity": "<snake_case>",
  "text": "<3-4 sentences>", "date": "<YYYY-MM-DD>"}}.
- facts: at least {facts}, each {{"id", "entity", "attribute", "text", "date": "<YYYY-MM-DD> or null", "supersedes": "<id> or null"}};
  at least 4 undated; exactly {replaced} pairs where a later fact replaces an earlier value of the same entity and attribute
  (the later one names the old value: "X moved from A to B"), with "supersedes" set.
- corrections: {corrections}, each {{"entity", "content": "In the <entity> card never omit: <item>, <item>"}}.
- aliases: {aliases}, each {{"alias": "<snake_case other name>", "canonical": "<entity>"}}.
- episodes: {episodes}, each {{"id", "created_at": "<YYYY-MM-DDTHH:MM:SS>", "repl": "chat", "input", "output"}};
  exactly 3 of them with input starting "[pc2] " and repl "pc2:chat".
- Every date on or before as_of. Invented, varied, specific values: ports, versions, names, times, counts. Seed: {seed}.
questions: exactly these kinds and counts: {door}. Each {{"question", "expected": [["<token>", "<alt>"]],
  "forbidden": [["<retired value>"]] (only for kind replaced), "entity": "<entity or omit>", "validated": true,
  "kind", "evidence": ["<ids of the items that answer it>"]}}.
  - fact: answered by a fact. card: answered by a card, "entity" set. alias: asks through an alias's words.
  - replaced: asks the current value; forbidden is the old one. dated: the answer is a date or a time.
  - never_stored: asks something plausible about a real entity that NO item, alias or file contains; evidence [].
  - Expected tokens are short exact strings (a number, a name, a version), never words of the question.
abstention: exactly {abstention} objects {{"question", "entity"}} about invented things that appear nowhere in the
  world; 3 of the questions also name a real entity next to the invented one.
repo: {{"<file>.py": "<python source>"}}, 3 files, at least 12 functions in all, about the world's services.
"""


def prompt(name: str, seed: int, mix: dict) -> str:
    door = ", ".join(f"{n} {k}" for k, n in mix["door"].items())
    return SPEC.format(name=name, seed=seed, door=door, abstention=mix.get("abstention", 12),
                       cards=mix.get("cards", 8), facts=mix.get("facts", 30), aliases=mix.get("aliases", 6),
                       corrections=mix.get("corrections", 3), episodes=mix.get("episodes", 12),
                       replaced=mix["door"].get("replaced", 3))


def parse(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        d = json.loads(t)
    except json.JSONDecodeError as e:
        raise ValueError(f"not JSON: {e.msg}") from None
    if not all(k in d for k in ("world", "questions", "abstention", "repo")):
        raise ValueError("missing keys")
    return d


def gemini(model: str) -> Callable[[str], str]:
    key = os.environ.get("GOOGLE_API_KEY") or ""
    if not key:
        raise SystemExit("GOOGLE_API_KEY is not set")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def ask(p: str) -> str:
        body = json.dumps({"contents": [{"parts": [{"text": p}]}],
                           "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0}}).encode()
        req = urllib.request.Request(url, body, {"Content-Type": "application/json", "x-goog-api-key": key})
        with urllib.request.urlopen(req, timeout=600) as r:
            out = json.loads(r.read())
        return out["candidates"][0]["content"]["parts"][0]["text"]
    return ask


def _write(out: Path, d: dict) -> None:
    (out / "cases").mkdir(parents=True)
    (out / "repo").mkdir()
    (out / "world.json").write_text(json.dumps(d["world"], indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "cases" / "questions.json").write_text(json.dumps(d["questions"], indent=1, ensure_ascii=False) + "\n",
                                                  encoding="utf-8")
    (out / "cases" / "abstention.json").write_text(json.dumps(d["abstention"], indent=1, ensure_ascii=False) + "\n",
                                                   encoding="utf-8")
    for fname, src in d["repo"].items():
        (out / "repo" / Path(fname).name).write_text(src, encoding="utf-8")


def generate(out: Path, name: str, seed: int, ask: Callable[[str], str], mix: dict = validate_set.MIX_PUBLIC,
             attempts: int = 5, say: Callable[[str], None] = print, model: str = "", canary: bool = False) -> dict:
    out = Path(out)
    if out.exists():
        raise SystemExit(f"{out} exists: a set is never overwritten")
    p = prompt(name, seed, mix)
    for n in range(1, attempts + 1):
        try:
            d = parse(ask(p))
        except (ValueError, KeyError) as e:
            say(f"attempt {n}: rejected ({type(e).__name__})")
            continue
        problems = validate_set.check(d["world"], d["questions"], d["abstention"], d["repo"], mix)
        if any(problems.values()):
            say(f"attempt {n}: rejected, " + ", ".join(f"{r} {len(v)}" for r, v in problems.items() if v))
            continue
        if canary:
            token = "cnry" + secrets.token_hex(6)
            d["world"]["canary"] = token
            for f in d["world"]["facts"][:3]:
                f["text"] = f"{f['text']} (ref {token})"
        _write(out, d)
        meta = {"name": name, "version": "1", "written_by": f"{model or 'model'} via adebench.genset",
                "prompt_sha256": hashlib.sha256(p.encode()).hexdigest(), "seed": seed, "attempts": n,
                "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "validator": {r: 0 for r in validate_set.RULES}, "sha256": sets.sha256(out)}
        (out / "set.json").write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
        say(f"attempt {n}: accepted; {len(d['questions'])} questions, {len(d['abstention'])} abstention; "
            f"sha256 {meta['sha256'][:12]}")
        return meta
    if out.exists():
        shutil.rmtree(out)
    raise SystemExit(f"no valid set in {attempts} attempts")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="adebench.genset")
    ap.add_argument("--name", required=True)
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="gemini-3-flash-preview")
    ap.add_argument("--canary", action="store_true", help="plant a leak-detection token (holdout sets)")
    a = ap.parse_args(argv)
    generate(Path(a.out), a.name, a.seed, gemini(a.model), model=a.model, canary=a.canary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests and fix until green**

Run: `python -m pytest tests/test_genset.py tests/test_validate_set.py -q`
Expected: PASS.

- [ ] **Step 5: Commit (after the user's ok)**

```
A set generator: a fixed specification, validated, never printed

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

---

### Task 6: Generate and freeze `public2`

**Files:**
- Create: `sets/public2/` (by the generator)
- Modify: `README.md` (a line under *The leaderboard*: the sets, with their hashes)
- Test: `tests/test_sets.py`

**Interfaces:**
- Consumes: `genset` CLI (Task 5), `sets.load`, `sets.sha256`, `validate_set.check` (Tasks 1, 4).
- Produces: `sets/public2/{world.json, cases/, repo/, set.json}`, loadable by every importer with `--set sets/public2`.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_sets.py
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
```

- [ ] **Step 2: Generate (the user runs it or approves the run; it costs cents)**

Run: `python -m adebench.genset --name public2 --seed 20260930 --out sets/public2`
Expected: `attempt N: accepted; 24 questions, 12 abstention; sha256 ...`.

- [ ] **Step 3: Check it runs end to end on the synthetic memory**

Run: `ADEBENCH_SET=sets/public2 python -m adebench --adapter examples.synthetic:SyntheticAdapter --cases sets/public2/cases --repo sets/public2/repo --no-sandbox-test --history /tmp/p2`
Expected: a report with 24 door cases and 12 abstention cases, no ERROR. The synthetic adapter reads the default set at import time: make `examples/synthetic.py` load `sets.current()` instead of `sets.DEFAULT` so this works, and re-run the full test suite (the quick reference must not move).

- [ ] **Step 4: Run all tests**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit (after the user's ok)**

```
public2: the second public set, generated and frozen

24 door questions and 12 abstention questions on a history of about
60 items, written by gemini-3-flash-preview from the fixed
specification in adebench/genset.py and accepted by every validator
rule. sha256 in sets/public2/set.json.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```
