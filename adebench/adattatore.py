"""The adapter contract: everything the sections need from a memory system.

The sections never talk to a Brain directly. They call an object that
implements `Adattatore`, and the only thing that knows HTTP endpoints, SQLite
tables or column names is that object. `adebench.ade.AdattatoreADE` is the
implementation for an ADE Brain; to benchmark another memory system, write
a class with the same methods and point to it:

    python -m adebench --adattatore mymodule:MyAdapter
    ADEBENCH_ADATTATORE=mymodule:MyAdapter python -m adebench

Every method returns plain dicts/lists so that an implementation can be
written without importing anything from adebench. Methods marked "may return
empty" let a memory without that feature still run: the corresponding cases
are skipped or scored 0, and the report says why.
"""
from __future__ import annotations

import importlib
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Adattatore(Protocol):
    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        """True if the memory system answers."""

    def riscalda(self) -> float | None:
        """One warm-up query, outside the measures. Returns ms or None."""

    # ── doors: how a client receives an answer ────────────────────────────
    def porte(self) -> list[str]:
        """Names of the doors this memory exposes (the first is the default)."""

    def testo_della_porta(self, query: str, porta: str) -> tuple[str, dict]:
        """The TEXT a client of that door literally receives for a question,
        plus the raw answer: a dict that may contain
          summary (str)                — the composed answer, uncut
          schede  [ {key, content} ]   — entity cards used in the answer
          semantic [ {source, content} ]
          episodic [ {input_summary, output_summary, created_at, _fallback} ]
          working  [ {key, value} ]
          sconosciuti [str]            — terms the memory declared unknown
        Missing keys are fine: the checks that need them are skipped."""

    def chiedi(self, query: str) -> dict:
        """The raw answer of the default retrieval door (same dict as above)."""

    # ── entity cards, corrections, aliases (may return empty) ─────────────
    def schede(self) -> list[dict]:
        """[{entita, content, data}] — one per entity card."""

    def correzioni(self) -> list[dict]:
        """[{entita, content}] — owner corrections attached to an entity."""

    def alias(self) -> list[dict]:
        """[{alias, canonico}] — alternative names → canonical entity."""

    # ── facts and their lifecycle (may return empty) ──────────────────────
    def traccia_aggiornamenti(self) -> dict:
        """Measures of the fact-update mechanism: at least
        {superseded_vivi, relation_updates, archivio_per_motivo, quota_memoria_viva_v2}."""

    def quota_event_date(self) -> tuple[int, int]:
        """(facts with an event date, facts total)."""

    # ── episodes and time ─────────────────────────────────────────────────
    def giorni_recenti(self, quanti: int) -> list[str]:
        """The most recent distinct days (YYYY-MM-DD) with episodes."""

    def episodi_del_giorno(self, giorno: str, limit: int) -> list[dict]:
        """[{created_at, ...}] — episodes filtered by day, as the door does it."""

    def episodi_firmati(self, prefisso: str) -> int:
        """How many episodes carry a machine signature prefix (federation)."""

    # ── live state (working memory) ───────────────────────────────────────
    def working_scrivi(self, sessione: str, chiave: str, valore: str, ttl_ore: int) -> bool: ...
    def working_leggi(self, sessione: str, chiave: str) -> Any: ...
    def working_cancella(self, sessione: str) -> None: ...
    def working_eta_minuti(self, sessione: str, chiave: str) -> float | None:
        """Age in minutes of a live-state key, or None if absent."""

    # ── file search and graph (may return empty) ──────────────────────────
    def ricerca_file(self, query: str, limit: int) -> list[str]:
        """Paths (any separator) of the top files for a query."""

    def grafo_vicini(self, entita: str) -> int:
        """How many edges touch this entity in the knowledge graph."""

    def grafo_orfani(self) -> tuple[int, int]:
        """(fact nodes whose fact no longer exists, fact nodes total)."""

    def grafo_conteggi(self) -> dict:
        """{nodi, archi}."""

    # ── report-only ───────────────────────────────────────────────────────
    def salute(self) -> tuple[dict, list[str]]:
        """(measures, warnings) about the memory lifecycle. Free-form."""

    def porte_misurate(self) -> list[str]:
        """Endpoints whose latency and size are reported per door."""

    def tracce(self) -> list[dict]:
        """[{porta, ms, chars}] — one per call made during the run."""

    def sonda_porte(self, domande: list[str]) -> None:
        """Extra calls on the other doors, so that all of them get measured."""


_corrente: Adattatore | None = None


def carica(spec: str) -> Adattatore:
    """'package.module:ClassName' → instance."""
    modulo, _, classe = spec.partition(":")
    if not modulo or not classe:
        raise ValueError(f"adattatore non valido: {spec!r} (atteso 'modulo:Classe')")
    cls = getattr(importlib.import_module(modulo), classe)
    ist = cls()
    mancanti = [m for m in metodi_richiesti() if not callable(getattr(ist, m, None))]
    if mancanti:
        raise TypeError(f"{spec} non implementa: {', '.join(sorted(mancanti))}")
    return ist


def metodi_richiesti() -> list[str]:
    """The method names an adapter must implement (read off the Protocol)."""
    return sorted(n for n, v in vars(Adattatore).items()
                  if callable(v) and not n.startswith("_"))


def imposta(ada: Adattatore) -> None:
    global _corrente
    _corrente = ada


def corrente() -> Adattatore:
    if _corrente is None:
        from adebench.config import CFG
        imposta(carica(CFG.adattatore))
    return _corrente  # type: ignore[return-value]
