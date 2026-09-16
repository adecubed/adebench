"""The adapter contract: everything the sections need from a memory system.

The sections never talk to a memory system directly. They call an object
that implements `Adapter`, and the only thing that knows HTTP endpoints,
SQLite tables or column names is that object. `adebench.ade.AdeAdapter` is
the implementation for an ADE Brain; to benchmark another memory system,
write a class with the same methods and point to it:

    python -m adebench --adapter mymodule:MyAdapter
    ADEBENCH_ADAPTER=mymodule:MyAdapter python -m adebench

Every method returns plain dicts/lists so that an implementation can be
written without importing anything from adebench. Methods marked "may return
empty" let a memory without that feature still run: the corresponding cases
are SKIP (out of the score) and the report says why. A method that FAILS
(raises) becomes an ERROR case: never an empty value.
"""
from __future__ import annotations

import importlib
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Adapter(Protocol):
    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        """True if the memory system answers with a healthy status."""

    def warm_up(self) -> float | None:
        """One warm-up query, outside the measures. Returns ms or None."""

    # ── doors: how a client receives an answer ────────────────────────────
    def doors(self) -> list[str]:
        """Names of the doors this memory exposes (the first is the default)."""

    def door_text(self, query: str, door: str) -> tuple[str, dict]:
        """The TEXT a client of that door literally receives for a question,
        plus the raw answer: a dict that may contain
          summary (str)                — the composed answer, uncut
          cards    [ {key, content} ]  — entity cards used in the answer
          semantic [ {source, content} ]
          episodic [ {input_summary, output_summary, created_at, _fallback} ]
          working  [ {key, value} ]
          unknown_terms [str]          — terms the memory declared unknown
        Missing keys are fine: the checks that need them are skipped."""

    def ask(self, query: str) -> dict:
        """The raw answer of the default retrieval door (same dict as above)."""

    def door_cut(self, door: str) -> int | None:
        """The character budget of that door (what the client cuts at), or
        None when the door delivers everything. The margin of an answer is
        measured against this budget, not against the text that happened to
        come back: a 10-character answer under a 2,400 cut has 2,390
        characters of room, not zero."""

    # ── entity cards, corrections, aliases (may return empty) ─────────────
    def cards(self) -> list[dict]:
        """[{entity, content, date}] — one per entity card."""

    def corrections(self) -> list[dict]:
        """[{entity, content}] — owner corrections attached to an entity."""

    def aliases(self) -> list[dict]:
        """[{alias, canonical}] — alternative names → canonical entity."""

    # ── facts and their lifecycle (may return empty) ──────────────────────
    def update_trace(self) -> dict:
        """Measures of the fact-update mechanism, e.g.
        {superseded_live, relation_updates, archive_by_reason, v2_share}."""

    def event_date_share(self) -> tuple[int, int]:
        """(facts with an event date, facts total)."""

    # ── episodes and time ─────────────────────────────────────────────────
    def recent_days(self, n: int) -> list[str]:
        """The most recent distinct days (YYYY-MM-DD) with episodes."""

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        """[{created_at, ...}] — episodes filtered by day, as the door does it."""

    def signed_episodes(self, prefix: str) -> int:
        """How many episodes carry a machine signature prefix (federation)."""

    # ── live state (working memory) ───────────────────────────────────────
    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool: ...
    def working_read(self, session: str, key: str) -> Any: ...
    def working_clear(self, session: str) -> None: ...
    def working_age_minutes(self, session: str, key: str) -> float | None:
        """Age in minutes of a live-state key, or None if absent."""

    # ── file search and graph (may return empty) ──────────────────────────
    def file_search(self, query: str, limit: int) -> list[str]:
        """Paths (any separator) of the top files for a query."""

    def graph_edges(self, entity: str) -> int:
        """How many edges touch this entity in the knowledge graph."""

    def graph_orphans(self) -> tuple[int, int]:
        """(fact nodes whose fact no longer exists, fact nodes total)."""

    def graph_counts(self) -> dict:
        """{nodes, edges}."""

    # ── report-only ───────────────────────────────────────────────────────
    def health_report(self) -> tuple[dict, list[str]]:
        """(measures, warnings) about the memory lifecycle. Free-form."""

    def measured_doors(self) -> list[str]:
        """Endpoints whose latency and size are reported per door. The FIRST
        one is the retrieval door: the census section ranks its size."""

    def traces(self) -> list[dict]:
        """[{door, ms, chars, http}] — one per call made during the run."""

    def probe_doors(self, questions: list[str]) -> None:
        """Extra calls on the other doors, so that all of them get measured."""

    # ── optional (not required by the loader) ─────────────────────────────
    # def stored_mentions(self, phrase: str) -> int:
    #     """How many stored items (episodes, facts, notes) contain this
    #     phrase, case-insensitive. The abstention section uses it to warn
    #     when an invented entity of the golden set is found in the memory:
    #     the benchmark must not write its own answers into what it
    #     measures. Without this method the check is skipped."""
    # def declared_bytes(self) -> int | None:
    #     """Size in bytes of what this memory's MCP server declares in
    #     tools/list. With a callwitness census (--census) the report gives
    #     the declared-vs-returned ratio; without this method it says the
    #     ratio was not measured."""


_current: Adapter | None = None


def required_methods() -> list[str]:
    """The method names an adapter must implement (read off the Protocol)."""
    return sorted(n for n, v in vars(Adapter).items() if callable(v) and not n.startswith("_"))


def load(spec: str) -> Adapter:
    """'package.module:ClassName' → instance, checked against the contract."""
    module, _, cls_name = spec.partition(":")
    if not module or not cls_name:
        raise ValueError(f"invalid adapter spec: {spec!r} (expected 'module:Class')")
    cls = getattr(importlib.import_module(module), cls_name)
    inst = cls()
    missing = [m for m in required_methods() if not callable(getattr(inst, m, None))]
    if missing:
        raise TypeError(f"{spec} does not implement: {', '.join(missing)}")
    return inst


def use(adapter: Adapter) -> None:
    global _current
    _current = adapter


def current() -> Adapter:
    if _current is None:
        from adebench.config import CFG
        use(load(CFG.adapter))
    return _current  # type: ignore[return-value]
