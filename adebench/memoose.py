"""Adapter for Memoose (github.com/AndrewNgo-ini/memoose): a local graph memory.

Everything goes through Memoose's own CLI, `memoose --json ...`, which is the
same surface its 26 MCP tools expose; the report-only measures read the
dataset's SQLite file, opened read-only. No Memoose code is imported.

    pip install memoose
    MEMOOSE_DATA_DIR=... python -m adebench --adapter adebench.memoose:MemooseAdapter \\
        --cases my/cases --sandbox-test examples/memoose_sandbox_test.py

Memoose is two halves: a deterministic engine (the graph, the CLI, the tools)
and a harness of skills a model runs on top of it, which is what decides that
a sentence means `zetaprobe --listens_on--> port_9000` and calls supersede.
adebench measures the engine: no model runs inside the harness, so what is
scored here is what Memoose does on its own, and the skills' judgment is out
of the picture. The README says so next to the number.

Doors:
  recall  what an agent gets from `memoose recall` in its routed mode: the
          entities, the facts as triples, and the chunk summaries; no cut
          (ADEBENCH_MEMOOSE_CUT=N cuts it at N characters, to compare with a
          memory whose client has a budget, e.g. 2400)
  facts   `recall --mode facts`: the graph alone, without the lexical chunks,
          the narrower door that carries supersession

What maps and what does not (SKIP is honest, not a zero):
  cards          entity descriptions are the closest thing to a card; owner
                 corrections and aliases: none, those cases SKIP
  fact updates   read from the graph: superseded relations, declared
                 functional relations, open contradictions. The harness's own
                 update probe does NOT run (no write_fact): a fact reaches
                 Memoose as a triple a model extracted, and the engine alone
                 has no way to turn a sentence into one. Point --sandbox-test
                 at examples/memoose_sandbox_test.py, which exercises
                 Memoose's own supersession through its API
  time           facts carry `valid_from` as their age; session turns are the
                 episodes, filtered by day as `session timeline` does
  live state     a session's standing context: the canary travels as
                 "<key>: <value>" inside one of Memoose's own sections
                 (environment_facts), and the newest line of that key wins.
                 No TTL, so a canary lives until the session is forgotten
  files          Memoose indexes chunks, not a repository: SKIP
  graph          the whole point: edges per entity, orphan relations, counts
  declared bytes `memoose serve` over stdio: what its MCP server declares to an
                 agent before the first question; None when that extra is not installed

Cleanup: Memoose deletes entities, relations and sessions, but not a stored
chunk. Run it against a dataset of its own (`-d adebench`, the default here),
so everything the benchmark wrote goes away with `memoose -d adebench forget
--all` at the end.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import time
from datetime import datetime, timezone

from adebench import __version__
from adebench.ade import competing_payload
from adebench.config import CFG

DOORS = ("recall", "facts")


class MemooseError(RuntimeError):
    pass


class MemooseAdapter:
    def __init__(self) -> None:
        self.bin = os.environ.get("ADEBENCH_MEMOOSE_BIN") or shutil.which("memoose") or "memoose"
        self.dataset = os.environ.get("ADEBENCH_MEMOOSE_DATASET", "adebench")
        self.cut = int(os.environ.get("ADEBENCH_MEMOOSE_CUT", "0"))
        self.limit = int(os.environ.get("ADEBENCH_MEMOOSE_LIMIT", "10"))
        # the session-context section the live-state canary travels in: one of
        # Memoose's own, not a name of ours
        self.section = os.environ.get("ADEBENCH_MEMOOSE_SECTION", "environment_facts")
        # the session whose standing context rides along with every answer: a
        # Memoose agent is given it at session start, so the door carries it
        self.session = os.environ.get("ADEBENCH_MEMOOSE_SESSION", "adebench")
        data_dir = os.environ.get("MEMOOSE_DATA_DIR") or os.path.join(os.path.expanduser("~"), ".memoose")
        self.db = os.path.join(data_dir, f"{self.dataset}.sqlite")
        self._traces: list[dict] = []
        self._sessions: set[str] = set()

    # ── the one door to Memoose ───────────────────────────────────────────
    def _cli(self, args: list[str], timeout: float = 180, stdin: str | None = None) -> dict:
        cmd = [self.bin, "--json", "-d", self.dataset] + args
        t0 = time.perf_counter()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=timeout, input=stdin)
        except FileNotFoundError as e:
            raise MemooseError(f"memoose not found ({self.bin}): {e}") from e
        except subprocess.TimeoutExpired as e:
            raise MemooseError(f"memoose {args[0]}: timeout after {timeout}s") from e
        ms = (time.perf_counter() - t0) * 1000
        out = (r.stdout or "").strip()
        self._traces.append({"door": args[0], "ms": ms, "chars": len(out),
                             "http": 200 if r.returncode == 0 else 500})
        if r.returncode != 0:
            raise MemooseError(f"memoose {' '.join(args[:2])}: {(r.stderr or out)[:200]}")
        try:
            return json.loads(out) if out else {}
        except json.JSONDecodeError as e:
            raise MemooseError(f"memoose {args[0]}: not JSON: {out[:200]}") from e

    def _sql(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        """The dataset's own SQLite, opened read-only: the report-only
        measures (graph counts, provenance, session days) have no CLI."""
        if not os.path.exists(self.db):
            return []
        uri = "file:" + self.db.replace("\\", "/").replace(" ", "%20") + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            conn.row_factory = sqlite3.Row
            return list(conn.execute(query, params))

    @staticmethod
    def _day(epoch: float | None) -> str:
        if not epoch:
            return ""
        return datetime.fromtimestamp(float(epoch), timezone.utc).astimezone().strftime("%Y-%m-%d")

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        try:
            return isinstance(self._cli(["status"], timeout=60), dict)
        except MemooseError:
            return False

    def warm_up(self) -> float | None:
        t0 = time.perf_counter()
        try:
            self._cli(["recall", "hello", "-n", "1"], timeout=120)
        except MemooseError:
            return None
        return (time.perf_counter() - t0) * 1000

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return list(DOORS)

    def door_cut(self, door: str) -> int | None:
        return self.cut or None

    def _recall(self, query: str, door: str) -> dict:
        args = ["recall", query, "-n", str(self.limit)]
        if door == "facts":
            args += ["-m", "facts"]
        return self._cli(args)

    def _answer(self, query: str, door: str) -> dict:
        r = self._recall(query, door)
        semantic = []
        for f in r.get("facts", []) if isinstance(r.get("facts"), list) else []:
            line = f"{f.get('source', '')} {f.get('relation', '')} {f.get('target', '')}".strip()
            desc = str(f.get("description") or "")
            date = str(f.get("valid_from") or "")[:10]
            text = f"{line}. {desc}".strip()
            semantic.append({"source": "memoose:fact",
                             "content": f"[since {date}] {text}" if date else text})
        for c in r.get("chunks", []) if isinstance(r.get("chunks"), list) else []:
            text = str(c.get("summary") or c.get("text") or "").strip()
            if text:
                semantic.append({"source": "memoose:chunk", "content": text})
        # the card of an entity the question names, the way the other adapters
        # do it: recall returns its nearest entities whatever is asked, and a
        # client that showed them all would invent a card for anything
        ql = query.lower()
        cards = [{"key": f"card:{e.get('name', '')}", "content": str(e.get("description") or "")}
                 for e in r.get("entities", []) if isinstance(e, dict) and e.get("description")
                 and len(str(e.get("name", ""))) >= 3
                 and str(e.get("name", "")).lower().replace("_", " ") in ql.replace("_", " ")]
        # Memoose answers with what it found, never with prose: the door text
        # is the brief an agent receives, in the order recall returns it.
        working = self._standing_context()
        lines = [f"- {w['key']}: {w['value']}" for w in working]
        lines += [f"- {c['key'][5:]}: {c['content']}" for c in cards]
        lines += [s["content"] for s in semantic]
        return {"summary": "\n".join(lines), "semantic": semantic, "cards": cards,
                "episodic": [], "working": working, "unknown_terms": [], "_raw": r}

    def _standing_context(self) -> list[dict]:
        """The session's standing context, which Memoose hands an agent at
        session start: one line per key, the newest of each. It is the live
        state a client of this memory really receives."""
        out: dict[str, str] = {}
        for row in self._sql("SELECT content FROM session_context WHERE session_id = ? AND section = ? "
                             "AND retired_at IS NULL ORDER BY created_at", (self.session, self.section)):
            key, _, value = str(row["content"]).partition(":")
            if value.strip():
                out[key.strip()] = value.strip()
        return [{"key": k, "value": v} for k, v in out.items()]

    def door_text(self, query: str, door: str) -> tuple[str, dict]:
        r = self._answer(query, door)
        text = competing_payload(CFG.pressure) + r["summary"]
        return (text[:self.cut] if self.cut else text), r

    def ask(self, query: str) -> dict:
        return self._answer(query, CFG.door if CFG.door in DOORS else "recall")

    # ── entity cards ──────────────────────────────────────────────────────
    def cards(self) -> list[dict]:
        return [{"entity": r["name"], "content": r["description"] or "",
                 "date": self._day(r["updated_at"])}
                for r in self._sql("SELECT name, description, updated_at FROM entities "
                                   "WHERE description <> '' ORDER BY name")]

    def corrections(self) -> list[dict]:
        return []

    def aliases(self) -> list[dict]:
        return []

    # ── facts and their lifecycle ─────────────────────────────────────────
    def update_trace(self) -> dict:
        rows = self._sql("SELECT superseded_by IS NOT NULL AS gone, count(*) AS n FROM relations GROUP BY gone")
        live = sum(r["n"] for r in rows if not r["gone"])
        retired = sum(r["n"] for r in rows if r["gone"])
        reasons: dict[str, int] = {}
        for r in self._sql("SELECT action, count(*) AS n FROM provenance GROUP BY action"):
            reasons[str(r["action"])] = r["n"]
        functional = [r["name"] for r in self._sql("SELECT name FROM functional_relations ORDER BY name")]
        open_c = self._sql("SELECT count(*) AS n FROM contradictions WHERE resolved_by IS NULL")
        return {"superseded_live": retired, "relations_live": live,
                "archive_by_reason": reasons, "functional_relations": functional,
                "open_contradictions": open_c[0]["n"] if open_c else 0}

    def event_date_share(self) -> tuple[int, int]:
        rows = self._sql("SELECT count(*) AS n, sum(valid_from IS NOT NULL) AS dated FROM relations "
                         "WHERE superseded_by IS NULL")
        if not rows or not rows[0]["n"]:
            return (0, 0)
        return (int(rows[0]["dated"] or 0), int(rows[0]["n"]))

    # ── episodes and time: a session's turns ──────────────────────────────
    def recent_days(self, n: int) -> list[str]:
        days = {self._day(r["created_at"]) for r in self._sql("SELECT created_at FROM session_turns")}
        return sorted((d for d in days if d), reverse=True)[:n]

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        rows = self._sql("SELECT session_id, role, text, created_at FROM session_turns ORDER BY created_at")
        out, pending = [], None
        for r in rows:
            if self._day(r["created_at"]) != day:
                continue
            if r["role"] == "user":
                pending = r
            elif r["role"] == "assistant" and pending is not None:
                out.append({"created_at": datetime.fromtimestamp(pending["created_at"]).isoformat(),
                            "input_summary": pending["text"], "output_summary": r["text"]})
                pending = None
        return out[:limit]

    def signed_episodes(self, prefix: str) -> int:
        rows = self._sql("SELECT count(*) AS n FROM session_turns WHERE text LIKE ?", (prefix + "%",))
        return int(rows[0]["n"]) if rows else 0

    # ── live state: a session's context sections ──────────────────────────
    # Memoose's sections are a fixed vocabulary (goals, rules, preferences,
    # environment_facts, …), so the live-state key travels inside the text of
    # one section, "<key>: <value>", and the newest line of that key wins —
    # the way a client reads a session's standing context.
    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool:
        if session not in self._sessions:
            self._cli(["session", "start", session])
            self._sessions.add(session)
        self._cli(["session", "context", session, "--section", self.section,
                   "--text", f"{key}: {value}"])
        return True

    def working_read(self, session: str, key: str):
        rows = self._sql("SELECT content FROM session_context WHERE session_id = ? AND section = ? "
                         "AND retired_at IS NULL AND content LIKE ? ORDER BY created_at DESC LIMIT 1",
                         (session, self.section, key + ":%"))
        return rows[0]["content"].split(":", 1)[1].strip() if rows else None

    def working_clear(self, session: str) -> None:
        try:
            self._cli(["forget", "--session", session])
        except MemooseError:
            pass
        self._sessions.discard(session)

    def working_age_minutes(self, session: str, key: str) -> float | None:
        rows = self._sql("SELECT created_at FROM session_context WHERE session_id = ? AND section = ? "
                         "AND retired_at IS NULL AND content LIKE ? ORDER BY created_at DESC LIMIT 1",
                         (session, self.section, key + ":%"))
        if not rows:
            return None
        return (time.time() - float(rows[0]["created_at"])) / 60.0

    # ── files and graph ───────────────────────────────────────────────────
    def file_search(self, query: str, limit: int) -> list[str]:
        return []

    def graph_edges(self, entity: str) -> int:
        rows = self._sql(
            "SELECT count(*) AS n FROM relations r JOIN entities e "
            "ON e.id IN (r.source_id, r.target_id) WHERE lower(e.name) = lower(?) "
            "AND r.superseded_by IS NULL", (entity,))
        return int(rows[0]["n"]) if rows else 0

    def graph_orphans(self) -> tuple[int, int]:
        rows = self._sql(
            "SELECT count(*) AS n, sum(s.id IS NULL OR t.id IS NULL) AS orphans FROM relations r "
            "LEFT JOIN entities s ON s.id = r.source_id LEFT JOIN entities t ON t.id = r.target_id")
        if not rows or not rows[0]["n"]:
            return (0, 0)
        return (int(rows[0]["orphans"] or 0), int(rows[0]["n"]))

    def graph_counts(self) -> dict:
        nodes = self._sql("SELECT count(*) AS n FROM entities")
        edges = self._sql("SELECT count(*) AS n FROM relations WHERE superseded_by IS NULL")
        return {"nodes": nodes[0]["n"] if nodes else 0, "edges": edges[0]["n"] if edges else 0}

    # ── report-only ───────────────────────────────────────────────────────
    def health_report(self) -> tuple[dict, list[str]]:
        measures, warnings = {}, []
        measures.update(self.graph_counts())
        chunks = self._sql("SELECT count(*) AS n FROM chunks")
        measures["chunks"] = chunks[0]["n"] if chunks else 0
        trace = self.update_trace()
        measures["superseded_relations"] = trace["superseded_live"]
        measures["functional_relations"] = len(trace["functional_relations"])
        if trace["open_contradictions"]:
            warnings.append(f"{trace['open_contradictions']} contradiction(s) waiting for judgment: "
                            "Memoose surfaces them, a model decides")
        if not trace["functional_relations"]:
            warnings.append("no functional relation declared: a second value for the same relation is "
                            "kept next to the first until something calls supersede")
        warnings.append("chunks are not deletable: what the benchmark writes goes away with the dataset")
        return measures, warnings

    def measured_doors(self) -> list[str]:
        return ["recall", "recall --mode facts"]

    def traces(self) -> list[dict]:
        return list(self._traces)

    def probe_doors(self, questions: list[str]) -> None:
        for q in questions[:2]:
            try:
                self._recall(q, "facts")
            except MemooseError:
                continue

    # ── optional ──────────────────────────────────────────────────────────
    def stored_mentions(self, phrase: str) -> int:
        like = f"%{phrase.lower()}%"
        rows = self._sql("SELECT (SELECT count(*) FROM chunks WHERE lower(coalesce(summary, text)) LIKE ?) "
                         "+ (SELECT count(*) FROM entities WHERE lower(name) LIKE ?) "
                         "+ (SELECT count(*) FROM session_turns WHERE lower(text) LIKE ?) AS n",
                         (like, like, like))
        return int(rows[0]["n"]) if rows else 0

    def declared_bytes(self) -> int | None:
        """What Memoose's MCP server puts in an agent's context before a
        question is asked: its tools/list, asked of `memoose serve` over
        stdio. None when the MCP server cannot start on this machine (it is
        an extra of the package, the CLI works without it)."""
        req = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "adebench", "version": __version__}}},
               {"jsonrpc": "2.0", "method": "notifications/initialized"},
               {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}]
        try:
            r = subprocess.run([self.bin, "serve"], capture_output=True, text=True, timeout=60,
                               encoding="utf-8", errors="replace",
                               input="\n".join(json.dumps(m) for m in req) + "\n")
        except (OSError, subprocess.TimeoutExpired):
            return None
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            if msg.get("id") == 2 and isinstance(msg.get("result"), dict):
                return len(json.dumps(msg["result"], separators=(",", ":")).encode("utf-8"))
        return None
