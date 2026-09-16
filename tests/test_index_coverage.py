"""The health section counts indexed rows against stored rows.

On 2026-09-16 the reference Brain's full-text index over episodes held 15
rows out of 2,689 for four days: the startup rebuild checked COUNT(*) on the
FTS table, which for an external-content index reads the content table and
so never saw an empty index. Retrieval kept answering through the other
sources and the benchmark scored the delivered text at 95. Nothing looked at
the index. This measure does."""
from __future__ import annotations

import sqlite3

import pytest

from adebench import ade, client


@pytest.fixture
def brain_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "_db_dir", tmp_path)
    return tmp_path


def _episodic_db(path, rows: int, index_after: bool):
    """Rows written before the index existed are exactly the production case."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE episodic_memory (id INTEGER PRIMARY KEY, task_id TEXT UNIQUE, "
                 "input_summary TEXT NOT NULL, output_summary TEXT, files_touched TEXT, result TEXT)")
    fts = ("CREATE VIRTUAL TABLE episodic_memory_fts USING fts5(input_summary, output_summary, "
           "files_touched, result, content='episodic_memory', content_rowid='id')")
    if not index_after:
        conn.execute(fts)
    for i in range(rows):
        conn.execute("INSERT INTO episodic_memory (task_id, input_summary) VALUES (?, ?)", (f"t{i}", f"episode {i}"))
        if not index_after:
            conn.execute("INSERT INTO episodic_memory_fts(rowid, input_summary) VALUES (?, ?)", (i + 1, f"episode {i}"))
    if index_after:
        conn.execute(fts)
    conn.commit()
    conn.close()


def test_index_created_after_the_rows_covers_nothing_and_warns(brain_dir):
    _episodic_db(brain_dir / "brain_episodic.db", 20, index_after=True)

    measures, warnings = ade.index_coverage()

    assert measures["episodic_memory_fts"] == {"stored": 20, "indexed": 0}
    assert warnings == ["index episodic_memory_fts covers 0 of 20 stored rows"]


def test_aligned_index_has_no_warning(brain_dir):
    _episodic_db(brain_dir / "brain_episodic.db", 5, index_after=False)

    measures, warnings = ade.index_coverage()

    assert measures["episodic_memory_fts"] == {"stored": 5, "indexed": 5}
    assert warnings == []


def test_missing_index_is_not_measured(brain_dir):
    conn = sqlite3.connect(brain_dir / "brain_episodic.db")
    conn.execute("CREATE TABLE episodic_memory (id INTEGER PRIMARY KEY, input_summary TEXT)")
    conn.execute("INSERT INTO episodic_memory (input_summary) VALUES ('x')")
    conn.commit()
    conn.close()

    measures, warnings = ade.index_coverage()

    assert "episodic_memory_fts" not in measures
    assert warnings == []
