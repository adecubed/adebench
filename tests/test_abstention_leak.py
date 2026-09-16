"""The invented entities of the abstention set must not be in the memory.

2026-09-16: an episode recorded by the benchmark's own author described the
abstention work and named one of the invented entities. Once indexed, the
memory 'knew' it and stopped abstaining: the benchmark had written its own
answer into the thing it measures. The abstention section now asks the
adapter whether each invented entity is stored anywhere and warns; the
adapter method is optional, a memory without it is simply not checked."""
from __future__ import annotations

import json
import sqlite3

import pytest

from adebench import adapter, ade, client, sections
from tests.test_adebench import Fake, cases  # noqa: F401 — fixture


class Leaky(Fake):
    def __init__(self, stored: dict[str, int]):
        super().__init__(answer={"summary": "nessun riscontro", "episodic": [], "semantic": []})
        self._stored = stored

    def stored_mentions(self, phrase: str) -> int:
        return self._stored.get(phrase.lower(), 0)


def _abstention(cases, entries):
    (cases / "abstention.json").write_text(json.dumps(entries), encoding="utf-8")
    return sections.abstention()


def test_entity_found_in_the_memory_is_a_warning(cases):
    adapter.use(Leaky({"girandola notturna": 1}))
    s = _abstention(cases, [{"question": "Cosa fa il workflow Girandola Notturna?", "entity": "Girandola Notturna"},
                            {"question": "Cos'e' il modulo Zarpetta?", "entity": "Zarpetta"}])
    assert s["warnings"] == ["'Girandola Notturna' is stored in 1 place(s): the abstention set leaked into the memory"]
    assert s["measures"]["leaked_entities"] == 1


def test_plain_questions_and_adapters_without_the_method_are_not_checked(cases):
    adapter.use(Fake(answer={"summary": "nessun riscontro"}))
    s = _abstention(cases, ["Cos'e' il modulo Zarpetta?"])
    assert s["warnings"] == []
    assert "leaked_entities" not in s["measures"]


def test_ade_counts_mentions_in_live_and_archived_episodes_and_facts(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "_db_dir", tmp_path)
    e = sqlite3.connect(tmp_path / "brain_episodic.db")
    e.execute("CREATE TABLE episodic_memory (id INTEGER PRIMARY KEY, input_summary TEXT, output_summary TEXT)")
    e.execute("CREATE TABLE episodic_archive (id INTEGER PRIMARY KEY, input_summary TEXT, output_summary TEXT)")
    e.execute("INSERT INTO episodic_memory (input_summary, output_summary) VALUES ('adebench: astensione', 'Girandola Notturna fallisce')")
    e.execute("INSERT INTO episodic_archive (input_summary, output_summary) VALUES ('vecchio', NULL)")
    e.commit(); e.close()
    s = sqlite3.connect(tmp_path / "brain_semantic.db")
    s.execute("CREATE TABLE semantic_memory (id INTEGER PRIMARY KEY, content TEXT, superseded INTEGER DEFAULT 0)")
    s.execute("INSERT INTO semantic_memory (content) VALUES ('il workflow GIRANDOLA notturna gira di notte')")
    s.commit(); s.close()

    assert ade.AdeAdapter().stored_mentions("Girandola Notturna") == 2
    assert ade.AdeAdapter().stored_mentions("Zarpetta") == 0
