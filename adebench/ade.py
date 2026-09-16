"""The adapter for an ADE Brain: HTTP on its endpoints, read-only SQLite on
its databases. This is the only file that knows the Brain's API. To bench
another memory system, write another class with the same methods (see
adebench/adapter.py) and point --adapter to it."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

from adebench import client
from adebench.client import ErrorResponse, ServiceDown, get, post, delete, sql, columns
from adebench.config import CFG

DOORS = ("voice", "agent", "raw", "two-step")


def competing_payload(chars: int) -> str:
    """A simulated block of the size a bad day would put before the answer:
    a long tool response, an oversized events block, a verbose episode.
    Deterministic text, clearly labelled, never containing golden words."""
    if chars <= 0:
        return ""
    line = "COMPETING PAYLOAD (simulated, adebench --pressure): lorem ipsum dolor sit amet consectetur "
    return (line * (chars // len(line) + 1))[:chars] + "\n\n"


class AdeAdapter:
    """Doors:
      voice — the voice client (Sofia Server): its sources, its "latest
              events" block, card first, its cut
      two-step — the Brain's brief (one identifier per item) plus
              GET /sofia/item fetches, composed under the voice cut
      agent — what an MCP agent gets: orchestrator context + semantic
              search, no cut
      raw   — /sofia/ask with the Brain's default sources and no cut
              (upper bound of what retrieval can deliver)
    """

    def __init__(self) -> None:
        self._events: str | None = None

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        return bool(client.health())

    def warm_up(self) -> float | None:
        return client.warm_up()

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return list(DOORS)

    def _sources(self, door: str) -> list[str]:
        return CFG.voice_sources if door == "voice" else []

    def door_cut(self, door: str) -> int | None:
        return CFG.voice_cut if door in ("voice", "two-step") else None

    def _two_step(self, query: str) -> tuple[str, dict]:
        """The Brain's two-step door: POST /sofia/ask with brief=true gives a
        brief with one identifier per item (scheda:, fact:, episode:,
        working:), GET /sofia/item?id= gives the full text of one item. The
        composition rule is adebench.twostep.compose, under the voice cut."""
        from adebench.twostep import compose
        t0 = time.perf_counter()
        r = post("/sofia/ask", {"query": query, "sources": self._sources("voice"), "include_raw": True, "brief": True})
        if not isinstance(r, dict):
            return "", {"summary": ""}
        raw = r.get("raw") or {}
        out = {"summary": r.get("summary") or "", "items": r.get("items") or []}
        for theirs, ours in {"schede": "cards", "semantic": "semantic", "episodic": "episodic",
                             "working": "working", "sconosciuti": "unknown_terms"}.items():
            if theirs in raw:
                out[ours] = raw[theirs]

        def fetch(item_id: str) -> str:
            try:
                d = get("/sofia/item", id=item_id)
            except (ServiceDown, ErrorResponse):
                return ""
            return str(d.get("text") or "") if isinstance(d, dict) else ""

        text, info = compose(out["summary"], out["items"], fetch, CFG.voice_cut, competing_payload(CFG.pressure),
                             detail_chars=int(os.environ.get("ADEBENCH_TWO_STEP_DETAIL_CHARS", "0")))
        out["_ms"] = round((time.perf_counter() - t0) * 1000)
        out["_two_step"] = info
        return text, out

    def ask(self, query: str, door: str | None = None) -> dict:
        door = door or CFG.door
        r = client.ask(query, self._sources(door), include_raw=True)
        raw = r.get("raw") or {}
        out = {"summary": r.get("summary") or "", "_ms": r.get("_ms", 0)}
        mapping = {"schede": "cards", "semantic": "semantic", "episodic": "episodic",
                   "working": "working", "sconosciuti": "unknown_terms"}
        for theirs, ours in mapping.items():
            if theirs in raw:
                out[ours] = raw[theirs]
        return out

    def _events_block(self) -> str:
        """Replica of the LATEST EVENTS block the voice client puts before
        the answer when there is no entity card."""
        if self._events is not None:
            return self._events
        lines, per_source = [], {}
        eps = get("/memory/episodic/recent", limit=15)
        for e in eps if isinstance(eps, list) else []:
            if not isinstance(e, dict):
                continue
            src = str(e.get("repl", "?"))
            if per_source.get(src, 0) >= 3:
                continue
            per_source[src] = per_source.get(src, 0) + 1
            lines.append(f"[{str(e.get('created_at', ''))[:10]}] ({src}) "
                         f"{str(e.get('input_summary', ''))[:130]}")
            if len(lines) >= 8:
                break
        self._events = ("ULTIMI EVENTI (dal più recente; sofia_server = le tue giornate, "
                        "claude_code = lavoro al PC):\n" + "\n".join(lines) + "\n\n") if lines else ""
        return self._events

    def _as_voice_hears(self, summary: str) -> str:
        events = self._events_block() if CFG.events_block else ""
        events = competing_payload(CFG.pressure) + events
        if "▣" in summary:
            return (summary + "\n\n" + events)[:CFG.voice_cut]
        return (events + summary)[:CFG.voice_cut]

    def door_text(self, query: str, door: str) -> tuple[str, dict]:
        if door == "two-step":
            return self._two_step(query)
        r = self.ask(query, door)
        summary = r["summary"]
        if door == "voice":
            return self._as_voice_hears(summary), r
        if door == "agent":
            ctx = post("/brain/orchestrator/context", {"user_input": query, "limit_semantic": 5})
            text = (ctx.get("context") or "") if isinstance(ctx, dict) else ""
            sem = post("/memory/semantic/search", query=query, limit=5)
            if isinstance(sem, list):
                text += "\n" + "\n".join(str(x.get("content", "")) for x in sem if isinstance(x, dict))
            return text, r
        return summary, r

    # ── entity cards ──────────────────────────────────────────────────────
    def cards(self) -> list[dict]:
        return [{"entity": r["key"].split(":", 1)[1], "content": r["content"] or "",
                 "date": r.get("last_reinforced") or r.get("created_at") or ""}
                for r in sql("brain_semantic.db",
                             "SELECT key, content, last_reinforced, created_at FROM semantic_memory "
                             "WHERE relation_type='scheda' AND superseded=0 ORDER BY key")]

    def corrections(self) -> list[dict]:
        out = []
        for r in sql("brain_semantic.db", "SELECT key, content FROM semantic_memory "
                                          "WHERE relation_type='correzione' AND superseded=0 ORDER BY key"):
            parts = r["key"].split(":")  # correzione:<entity>:<timestamp>
            out.append({"entity": parts[1] if len(parts) > 1 else "", "content": r["content"] or ""})
        return out

    def aliases(self) -> list[dict]:
        return [{"alias": r["alias"], "canonical": r["canonico"]}
                for r in sql("brain_graph.db", "SELECT alias, canonico FROM entity_alias")]

    # ── facts ─────────────────────────────────────────────────────────────
    def update_trace(self) -> dict:
        live = sql("brain_semantic.db", "SELECT relation_type, superseded, key FROM semantic_memory")
        n_sup = sum(1 for r in live if r["superseded"])
        n_upd = sum(1 for r in live if r["relation_type"] == "updates")
        reasons = {}
        has_v2 = "motivo" in columns("brain_semantic.db", "semantic_archive")
        if has_v2:
            for r in sql("brain_semantic.db", "SELECT motivo, count(*) n FROM semantic_archive GROUP BY motivo"):
                reasons[str(r["motivo"])] = r["n"]

        def _v2(r):
            if r["relation_type"] in ("updates", "derives", "extends", "merged"):
                return True
            return r["relation_type"] == "fact" and not r["key"].startswith(("cross_", "folder:"))
        alive = [r for r in live if not r["superseded"]
                 and r["relation_type"] not in ("scheda", "correzione", "antipattern")]
        share = (sum(1 for r in alive if _v2(r)) / len(alive)) if alive else 0.0
        return {"superseded_live": n_sup, "relation_updates": n_upd, "archive_by_reason": reasons,
                "archive_has_v2_columns": has_v2, "v2_share": round(share, 3)}

    def event_date_share(self) -> tuple[int, int]:
        r = sql("brain_semantic.db",
                "SELECT count(*) n, sum(CASE WHEN event_date IS NOT NULL AND event_date!='' THEN 1 ELSE 0 END) d "
                "FROM semantic_memory WHERE superseded=0 AND relation_type NOT IN ('scheda','correzione','antipattern')")
        return (r[0]["d"] or 0, r[0]["n"]) if r else (0, 0)

    # ── episodes ──────────────────────────────────────────────────────────
    def recent_days(self, n: int) -> list[str]:
        return [r["g"] for r in sql("brain_episodic.db",
                                    "SELECT DISTINCT substr(created_at,1,10) g FROM episodic_memory "
                                    "ORDER BY g DESC LIMIT ?", n)]

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        eps = get("/memory/episodic/recent", limit=limit, day=day)
        return eps if isinstance(eps, list) else []

    def signed_episodes(self, prefix: str) -> int:
        r = sql("brain_episodic.db", "SELECT count(*) n FROM episodic_memory WHERE input_summary LIKE ?",
                prefix + "%")
        return r[0]["n"] if r else 0

    # ── working memory ────────────────────────────────────────────────────
    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool:
        w = post("/memory/working/write", {"session_id": session, "key": key, "value": value,
                                            "repl": "adebench", "ttl_hours": ttl_hours})
        return bool(isinstance(w, dict) and w.get("ok"))

    def working_read(self, session: str, key: str) -> Any:
        return get("/memory/working/read", session_id=session, key=key)

    def working_clear(self, session: str) -> None:
        delete("/memory/working/clear", session_id=session)

    def working_age_minutes(self, session: str, key: str) -> float | None:
        r = sql("brain_working.db", "SELECT created_at FROM working_memory WHERE session_id=? AND key=?",
                session, key)
        if not r or not r[0].get("created_at"):
            return None
        t = datetime.fromisoformat(str(r[0]["created_at"]).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 60

    # ── files and graph ───────────────────────────────────────────────────
    def file_search(self, query: str, limit: int) -> list[str]:
        r = post("/brain/memory/tool/search", {"query": query, "limit": limit})
        return [str(x.get("key", "")) for x in (r if isinstance(r, list) else []) if isinstance(x, dict)]

    def graph_edges(self, entity: str) -> int:
        g = get("/memory/graph/query", slug=entity, depth=1, limit=50)
        return len(g.get("edges", [])) if isinstance(g, dict) else 0

    def graph_orphans(self) -> tuple[int, int]:
        facts = {r["key"] for r in sql("brain_semantic.db", "SELECT key FROM semantic_memory")}
        nodes = [r["slug"] for r in sql("brain_graph.db", "SELECT slug FROM graph_nodes WHERE slug LIKE 'fact:%'")]
        return sum(1 for s in nodes if s[5:] not in facts), len(nodes)

    def graph_counts(self) -> dict:
        n = sql("brain_graph.db", "SELECT count(*) n FROM graph_nodes")
        e = sql("brain_graph.db", "SELECT count(*) n FROM graph_edges")
        return {"nodes": n[0]["n"] if n else 0, "edges": e[0]["n"] if e else 0}

    # ── report-only ───────────────────────────────────────────────────────
    def health_report(self) -> tuple[dict, list[str]]:
        m: dict = {}
        m["index_coverage"], warnings = index_coverage()
        live = sql("brain_semantic.db", "SELECT relation_type, key, confidence, content FROM semantic_memory WHERE superseded=0")
        m["live_facts"] = len(live)
        arch = sql("brain_semantic.db", "SELECT count(*) n FROM semantic_archive")
        m["archived_facts"] = arch[0]["n"] if arch else 0
        by_type: dict = {}
        producers = {"cross_": 0, "folder:": 0, "distiller/other": 0}
        for r in live:
            by_type[r["relation_type"]] = by_type.get(r["relation_type"], 0) + 1
            if r["relation_type"] == "fact":
                k = "cross_" if r["key"].startswith("cross_") else "folder:" if r["key"].startswith("folder:") else "distiller/other"
                producers[k] += 1
        m["by_relation_type"] = by_type
        m["facts_by_producer"] = producers
        m["at_floor_0.3"] = sum(1 for r in live if (r["confidence"] or 0) <= 0.31)
        m["mojibake"] = sum(1 for r in live if "�" in (r["content"] or "") or "Ã" in (r["content"] or ""))
        pend = get("/memory/episodic/pending")
        m["episodes_to_distill"] = pend.get("pending") if isinstance(pend, dict) else None
        st = get("/brain/stats")
        m["unacknowledged_anomalies"] = st.get("unacknowledged_anomalies") if isinstance(st, dict) else None
        ep = sql("brain_episodic.db", "SELECT count(*) n FROM episodic_memory")
        m["episodes"] = ep[0]["n"] if ep else 0
        if m["mojibake"]:
            warnings.append(f"{m['mojibake']} live facts with corrupted text (mojibake)")
        if (m["unacknowledged_anomalies"] or 0) > 1000:
            warnings.append(f"{m['unacknowledged_anomalies']} observer anomalies never acknowledged")
        if producers["cross_"] > producers["distiller/other"] * 3:
            warnings.append("live memory is dominated by cross-learning patterns")
        return m, warnings

    def measured_doors(self) -> list[str]:
        return ["/sofia/ask", "/brain/memory/tool/search", "/brain/orchestrator/context"]


# The full-text indexes of the Brain and the table each one is built from.
_FTS_INDEXES = (
    ("brain_episodic.db", "episodic_memory", "episodic_memory_fts"),
    ("brain_episodic.db", "episodic_archive", "episodic_archive_fts"),
    ("brain_semantic.db", "semantic_memory", "semantic_fts"),
)


def index_coverage() -> tuple[dict, list[str]]:
    """Indexed rows against stored rows, for every full-text index.

    Counted on the index's own docsize table: COUNT(*) on an external-content
    FTS5 table reads the content table and says nothing about the index —
    which is how the reference Brain ran four days with 15 episodes indexed
    out of 2,689 while the score stayed at 95. An index that is missing is
    not measured; one that covers fewer rows than stored is a warning."""
    measures: dict = {}
    warnings: list[str] = []
    for db, table, fts in _FTS_INDEXES:
        try:
            stored = sql(db, f"SELECT count(*) n FROM {table}")
            indexed = sql(db, f"SELECT count(*) n FROM {fts}_docsize")
        except Exception:  # noqa: BLE001 — no such table, no such index, or no docsize table
            continue
        if not stored or not indexed:
            continue
        measures[fts] = {"stored": stored[0]["n"], "indexed": indexed[0]["n"]}
        if indexed[0]["n"] < stored[0]["n"]:
            warnings.append(f"index {fts} covers {indexed[0]['n']} of {stored[0]['n']} stored rows")
    return measures, warnings

    def traces(self) -> list[dict]:
        return client.traces

    def probe_doors(self, questions: list[str]) -> None:
        for q in questions:
            post("/brain/memory/tool/search", {"query": q, "limit": 5})
            post("/brain/orchestrator/context", {"user_input": q, "limit_semantic": 5})
