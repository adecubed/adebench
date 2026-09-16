"""The episodic day filter is judged in the memory's own day, not in UTC.

2026-09-16: the reference Brain answered "episodes of 2026-09-15" with two
episodes stamped 2026-09-14T22:01Z — midnight in Rome, where the Brain
lives. The check compared the UTC prefix and failed a correct answer. Days
are compared in the local timezone; the timezone is explicit so the test
does not depend on the machine running it."""
from __future__ import annotations

import sqlite3
from zoneinfo import ZoneInfo

import pytest

from adebench import adapter, ade, client, config, sections
from tests.test_adebench import Fake, cases  # noqa: F401 — fixture

ROME = ZoneInfo("Europe/Rome")


@pytest.fixture
def rome(monkeypatch):
    monkeypatch.setattr(config, "LOCAL_TZ", ROME)


def test_local_day_moves_midnight_utc_into_the_next_local_day(rome):
    assert config.local_day("2026-09-14T22:01:30.308182+00:00") == "2026-09-15"
    assert config.local_day("2026-09-14T12:00:00+00:00") == "2026-09-14"
    # a stamp without offset is taken as it is
    assert config.local_day("2026-09-14T23:59:00") == "2026-09-14"
    assert config.local_day("2026-09-14") == "2026-09-14"


class Days(Fake):
    def __init__(self, day, stamps):
        super().__init__()
        self._day, self._stamps = day, stamps

    def recent_days(self, n): return [self._day]
    def episodes_of_day(self, d, limit): return [{"created_at": s} for s in self._stamps]


def _day_case(section):
    return next(c for c in section["cases"] if c["case"].startswith("day filter"))


def test_midnight_episode_belongs_to_the_local_day(rome, cases):
    adapter.use(Days("2026-09-15", ["2026-09-14T22:01:30+00:00", "2026-09-15T08:00:00+00:00"]))
    assert _day_case(sections.time_section())["status"] == "PASS"


def test_an_episode_of_another_day_still_fails(rome, cases):
    adapter.use(Days("2026-09-15", ["2026-09-14T12:00:00+00:00"]))
    assert _day_case(sections.time_section())["status"] == "FAIL"


def test_ade_recent_days_are_local_days(rome, tmp_path, monkeypatch):
    monkeypatch.setattr(client, "_db_dir", tmp_path)
    conn = sqlite3.connect(tmp_path / "brain_episodic.db")
    conn.execute("CREATE TABLE episodic_memory (id INTEGER PRIMARY KEY, created_at TEXT)")
    conn.executemany("INSERT INTO episodic_memory (created_at) VALUES (?)",
                     [("2026-09-14T22:01:30+00:00",), ("2026-09-14T10:00:00+00:00",), ("2026-09-12T10:00:00+00:00",)])
    conn.commit()
    conn.close()

    assert ade.AdeAdapter().recent_days(3) == ["2026-09-15", "2026-09-14", "2026-09-12"]
