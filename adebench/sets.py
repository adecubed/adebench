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
            "FACTS": [{"key": f["id"], "content": f["text"], "event_date": f.get("date"),
                       "entity": f.get("entity"), "attribute": f.get("attribute")} for f in self.facts],
            "EPISODES": [{"created_at": e["created_at"], "repl": e["repl"], "input_summary": e["input"],
                          "output_summary": e["output"]} for e in self.episodes],
        }


def fact_entity(fact: dict, cards: dict, default: str | None = None) -> str | None:
    """The card entity a fact is about: the world's own entity when it has a
    card, else the first card entity named in the fact's key (the quick set's
    keys are brain_port, mailbox_version...), else the default."""
    if fact.get("entity") in cards:
        return fact["entity"]
    return next((e for e in cards if e in fact["key"]), default)


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
    """The set named by --set <folder> or --set=<folder>, else ADEBENCH_SET, else
    sets/quick. It says which one it loaded (stderr): a run loaded with one set
    and scored on another's questions would look like a bad memory."""
    path = None
    for i, a in enumerate(sys.argv):
        if a == "--set":
            if i + 1 >= len(sys.argv) or sys.argv[i + 1].startswith("--"):
                raise SystemExit("--set needs a set folder")
            path = sys.argv[i + 1]
        elif a.startswith("--set="):
            path = a[len("--set="):] or None
            if path is None:
                raise SystemExit("--set needs a set folder")
    w = load(path or os.environ.get("ADEBENCH_SET") or DEFAULT)
    print(f"set: {w.name} ({w.path}) sha256 {sha256(w.path)[:12]}", file=sys.stderr)
    return w


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
