"""Adapter for Engram (github.com/Gentleman-Programming/engram): persistent
memory for coding agents, one Go binary over SQLite + FTS5, no model inside.

Everything an agent does goes through Engram's own MCP server, spoken over
stdio with the profile `engram setup` installs in an agent (`engram mcp
--tools=agent`, 19 tools): `mem_save` to write (title + content, `topic_key`
for an upsert), `mem_search` to read (a ranked list, each hit with its title,
a 300-character preview and its time), `mem_session_start`, `mem_save_prompt`
for what the user asked. That profile has no delete: removal goes through
Engram's CLI, `engram delete <id>` (a soft delete). A memory with an original
date goes through Engram's own import path, `engram import <file>`, the restore
of an `engram export`, which keeps `created_at`: `mem_save` has no date
argument and stamps the write time. The report-only measures (days, relations,
mentions) read Engram's SQLite file, opened read-only. No Engram code is linked.

    # Windows release binary, v2.2.1, checked against the release's checksums.txt
    set ENGRAM_BIN=C:/.../engram.exe
    set ENGRAM_DATA_DIR=C:/.../engram-data      # a FRESH scratch store, not ~/.engram
    python examples/engram_import.py
    python -m adebench --adapter adebench.engram:EngramAdapter --cases sets/quick/cases

    ENGRAM_BIN          the engram executable (default: `engram` on PATH)
    ENGRAM_DATA_DIR     Engram's data directory (engram.db lives there); Engram's
                        own default is ~/.engram
    ENGRAM_PROJECT      the Engram project measured (default adebench)
    ADEBENCH_ENGRAM_LIMIT  results per search (default 10, Engram's default; max 20)
    ADEBENCH_ENGRAM_CUT    cut the door text at N characters (default: no cut)

A run needs a FRESH ENGRAM_DATA_DIR, imported once: Engram's delete is soft,
and the conflict relations the probes' writes created stay behind in the store
(pending, pointing at deleted memories), so a second run on the same store
does not measure the same memory.

Doors:
  search      the question as it is, match_mode "any". The door text is the
              whole text the MCP tool returns to the agent: a JSON envelope
              whose `result` is the ranked list (title, preview, local time of
              each hit, pending-conflict notes) and whose `results` repeats the
              hits as structured fields. Nothing is re-rendered; the adapter
              parses it only to fill semantic/episodic/working
  search_all  the same with the tool's default match_mode "all": every word
              of the query must be in a memory. A question ending in "?" keeps
              the "?" on its last word, so a question asked as it is finds
              nothing here; an agent that sends keywords does better. The
              second door shows that, the first is the one scored

What maps and what does not (SKIP is honest, not a zero):
  cards          none: an observation has a title, not an entity card.
                 Corrections, aliases: none, those cases SKIP
  fact updates   `mem_save` of a new value does NOT replace the old one: Engram
                 finds the similar memory and marks a pending conflict for
                 the agent's model to judge (`mem_judge`); no model runs here,
                 so both values stay. `topic_key` is the upsert, but it is the
                 client naming what it replaces, which the harness probe does
                 not allow. write_fact: mem_save; forget_memory: engram delete
  time           one timestamp per observation, `created_at`: the write time
                 through mem_save, the original time through `engram import`.
                 Only the imported ones carry a date of their own (their sync
                 id says they came through import); a memory written by
                 mem_save gets no age, its write time is not the fact's. An
                 episode is a session with the user's prompt and the
                 observation of what was done; the day filter is done in the
                 adapter (no day tool), in adebench's LOCAL_TZ
  live state     `mem_save` with a topic_key per key: the upsert rewrites the
                 same observation, so the newest value is the only one. No TTL
  files          Engram stores observations, not a repository index: SKIP
  graph          relations link observations (supersedes, conflicts), not
                 entities: no entity has edges, SKIP
  declared bytes tools/list of `engram mcp --tools=agent`, the same server the
                 door talks to

Cleanup: `engram delete <id>` is a soft delete (the row stays, out of every
read). A user prompt has no soft delete: the one ingest_exchange writes is
removed with `engram delete prompt <id>`.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone

from adebench import config
from adebench.ade import competing_payload
from adebench.config import CFG

DOORS = ("search", "search_all")
_MODE = {"search": "any", "search_all": "all"}
TOOLS = "agent"             # the profile `engram setup` installs
IMPORTED = "obs-imported-"  # sync id of an observation that came in through import, with its own date


class EngramError(RuntimeError):
    pass


class _Mcp:
    """One MCP session with `engram mcp` over stdio, kept open on a
    background event loop and driven from synchronous code."""

    def __init__(self, cmd: str, args: list[str], env: dict, cwd: str | None) -> None:
        self.cmd, self.args, self.env, self.cwd = cmd, args, env, cwd
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.session = None
        self._stack = None
        self.tools: list = []
        self._run(self._open(), 60)

    def _run(self, coro, timeout: float = 120):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    async def _open(self):
        from contextlib import AsyncExitStack
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        self._stack = AsyncExitStack()
        params = StdioServerParameters(command=self.cmd, args=self.args, env=self.env, cwd=self.cwd)
        r, w = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(r, w))
        await self.session.initialize()
        self.tools = (await self.session.list_tools()).tools

    async def _call(self, name: str, args: dict):
        res = await self.session.call_tool(name, args)
        text = "".join(c.text for c in res.content if hasattr(c, "text"))
        data = None
        if text.strip().startswith("{"):
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = None
        return {"text": text, "data": data if isinstance(data, dict) else {},
                "error": bool(getattr(res, "isError", False))}

    def call(self, name: str, args: dict, timeout: float = 120) -> dict:
        return self._run(self._call(name, args), timeout)


def _utc(when: str) -> str:
    """An ISO date or datetime as Engram stores it: 'YYYY-MM-DD HH:MM:SS' UTC.
    A date alone is noon; a naive datetime is taken as UTC."""
    ts = when if "T" in when or " " in when else f"{when}T12:00:00"
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00").replace(" ", "T"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _utc_iso(stored: str) -> str:
    """Engram's stored 'YYYY-MM-DD HH:MM:SS' (UTC) as ISO with its offset."""
    try:
        return datetime.strptime(str(stored)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return ""


def _day(stored: str) -> str:
    """The day of a stored time, in adebench's LOCAL_TZ."""
    iso = _utc_iso(stored)
    return config.local_day(iso) if iso else ""


def title_of(text: str) -> str:
    """A title for a text that comes without one, the way Engram derives it
    itself when it captures a learning (store.PassiveCapture): the first 60
    characters, "..." when longer. mem_save requires a title; the harness
    gives only a text."""
    text = " ".join(str(text).split())
    return text if len(text) <= 60 else text[:60] + "..."


_HIT = re.compile(r"^\[\d+\] #(\d+) \([^)]*\) \S+ (.*?)\n    (.*?)\n    (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \|",
                  re.M | re.S)


def parse_search(result: str) -> dict[int, dict]:
    """The hits of mem_search's `result` text, by observation id: title,
    preview (without Engram's " [preview]" mark) and the time as printed (in
    Engram's display zone). A hit is a block like
      [1] #12 (manual) — title
          preview
          2026-03-01 13:00:00 | project: adebench | scope: project"""
    out = {}
    for m in _HIT.finditer(result or ""):
        preview = m.group(3).strip()
        if preview.endswith(" [preview]"):
            preview = preview[: -len(" [preview]")]
        out[int(m.group(1))] = {"title": m.group(2).strip(), "preview": preview, "shown_at": m.group(4)}
    return out


class EngramAdapter:
    def __init__(self) -> None:
        self.bin = os.environ.get("ENGRAM_BIN") or shutil.which("engram") or "engram"
        self.data_dir = os.environ.get("ENGRAM_DATA_DIR", "").strip() or os.path.join(os.path.expanduser("~"), ".engram")
        self.project = os.environ.get("ENGRAM_PROJECT", "adebench")
        self.limit = int(os.environ.get("ADEBENCH_ENGRAM_LIMIT", "10"))
        self.cut = int(os.environ.get("ADEBENCH_ENGRAM_CUT", "0"))
        self.db = os.path.join(self.data_dir, "engram.db")
        self._traces: list[dict] = []
        self._mcp: _Mcp | None = None
        self._live: dict[tuple[str, str], int] = {}   # (session, key) -> observation id

    # ── the MCP door ──────────────────────────────────────────────────────
    def _env(self) -> dict:
        env = dict(os.environ)
        env["ENGRAM_DATA_DIR"] = self.data_dir
        env["ENGRAM_PROJECT"] = self.project
        return env

    def _conn(self) -> _Mcp:
        if self._mcp is None:
            try:
                self._mcp = _Mcp(self.bin, ["mcp", f"--tools={TOOLS}", "--project", self.project],
                                 self._env(), self.data_dir)
            except Exception as e:  # noqa: BLE001
                raise EngramError(f"cannot start engram mcp: {type(e).__name__}: {str(e)[:120]}") from e
        return self._mcp

    def _tool(self, name: str, args: dict, door: str | None = None, timeout: float = 120) -> dict:
        t0 = time.perf_counter()
        try:
            out = self._conn().call(name, args, timeout)
        except EngramError:
            raise
        except Exception as e:  # noqa: BLE001
            self._traces.append({"door": door or name, "ms": (time.perf_counter() - t0) * 1000, "chars": 0, "http": 500})
            raise EngramError(f"{name}: {type(e).__name__}: {e}") from e
        self._traces.append({"door": door or name, "ms": (time.perf_counter() - t0) * 1000,
                             "chars": len(out.get("text", "")), "http": 500 if out["error"] else 200})
        if out["error"]:
            raise EngramError(f"{name}: {out.get('text', '')[:200]}")
        return out

    def _cli(self, args: list[str], timeout: float = 120) -> str:
        t0 = time.perf_counter()
        try:
            r = subprocess.run([self.bin] + args, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout, env=self._env(), cwd=self.data_dir)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise EngramError(f"engram {args[0]}: {type(e).__name__}") from e
        self._traces.append({"door": f"cli {args[0]}", "ms": (time.perf_counter() - t0) * 1000,
                             "chars": len(r.stdout or ""), "http": 200 if r.returncode == 0 else 500})
        if r.returncode != 0:
            raise EngramError(f"engram {' '.join(args[:2])}: {(r.stderr or r.stdout)[:200]}")
        return r.stdout or ""

    def _sql(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Engram's SQLite, read-only, for what no tool reports (days,
        sessions, relations). A missing store is an error, not an empty one."""
        if not os.path.exists(self.db):
            raise EngramError("no engram.db in ENGRAM_DATA_DIR")
        uri = "file:" + self.db.replace("\\", "/").replace(" ", "%20") + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            return list(conn.execute(query, params))

    # ── writing ───────────────────────────────────────────────────────────
    def save(self, title: str, content: str, session: str | None = None, topic_key: str | None = None) -> int | None:
        args = {"title": title, "content": content, "capture_prompt": False}
        if session:
            args["session_id"] = session
        if topic_key:
            args["topic_key"] = topic_key
        d = self._tool("mem_save", args)["data"]
        return int(d["id"]) if d.get("id") else None

    def save_prompt(self, content: str, session: str) -> int | None:
        self._tool("mem_save_prompt", {"content": content, "session_id": session})
        rows = self._sql("SELECT id FROM user_prompts WHERE session_id = ? AND content = ? ORDER BY id DESC LIMIT 1",
                         (session, content))
        return int(rows[0]["id"]) if rows else None

    def import_export(self, data: dict) -> str:
        """Engram's own import path (`engram import <file>`, the restore of an
        export): the one that keeps an observation's created_at."""
        fd, path = tempfile.mkstemp(suffix=".json", prefix="adebench-engram-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
            return self._cli(["import", path])
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    @staticmethod
    def export_record(title: str, content: str, created_at: str, session: str, project: str,
                      prompt: str | None = None) -> dict:
        """One observation (and optionally the user's prompt before it) in
        Engram's export format, at its own time. Its sync id says it came
        through import, which is how the adapter tells a date of its own from
        a write time later."""
        ts = _utc(created_at)
        obs = {"sync_id": IMPORTED + uuid.uuid4().hex[:16], "session_id": session, "type": "manual",
               "title": title, "content": content, "project": project, "scope": "project",
               "revision_count": 1, "duplicate_count": 1, "last_seen_at": ts, "created_at": ts,
               "updated_at": ts, "pinned": False}
        rec = {"session": {"id": session, "project": project, "ownership_mode": "shared",
                           "directory": "", "started_at": ts},
               "observation": obs, "prompt": None}
        if prompt:
            rec["prompt"] = {"sync_id": "prompt-" + uuid.uuid4().hex[:16], "session_id": session,
                             "content": prompt, "project": project, "created_at": ts}
        return rec

    @staticmethod
    def export_file(records: list[dict]) -> dict:
        sessions = {}
        for r in records:
            sessions.setdefault(r["session"]["id"], r["session"])
        return {"version": "0.2.0", "exported_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                "sessions": list(sessions.values()), "observations": [r["observation"] for r in records],
                "prompts": [r["prompt"] for r in records if r["prompt"]]}

    def _id_of(self, sync_id: str) -> int | None:
        rows = self._sql("SELECT id FROM observations WHERE sync_id = ?", (sync_id,))
        return int(rows[0]["id"]) if rows else None

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        # the MCP server answers, resolves the measured project, and its store
        # is on disk where the adapter reads it
        try:
            out = self._tool("mem_current_project", {}, timeout=60)
        except EngramError:
            return False
        return out["data"].get("project") == self.project and os.path.exists(self.db)

    def warm_up(self) -> float | None:
        t0 = time.perf_counter()
        try:
            self._search("hello", "search", 1)
        except EngramError:
            return None
        return (time.perf_counter() - t0) * 1000

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return list(DOORS)

    def door_cut(self, door: str) -> int | None:
        return self.cut or None

    def _search(self, query: str, door: str, limit: int | None = None) -> dict:
        args = {"query": query, "limit": limit or self.limit}
        if _MODE[door] != "all":
            args["match_mode"] = _MODE[door]
        return self._tool("mem_search", args, door=f"mem_search {_MODE[door]}")

    def _rows(self, ids: list[int]) -> dict[int, sqlite3.Row]:
        if not ids:
            return {}
        q = ("SELECT o.id, o.sync_id, o.created_at, "
             "(SELECT count(*) FROM user_prompts p WHERE p.session_id = o.session_id) AS prompts "
             f"FROM observations o WHERE o.id IN ({','.join('?' * len(ids))})")
        return {int(r["id"]): r for r in self._sql(q, tuple(ids))}

    def _answer(self, query: str, door: str) -> dict:
        out = self._search(query, door)
        d = out["data"]
        text = out["text"]   # what the agent receives: the tool's whole text
        hits = [h for h in d.get("results") or [] if isinstance(h, dict)]
        rows = self._rows([int(h["id"]) for h in hits if h.get("id")])
        parsed = parse_search(str(d.get("result") or ""))
        semantic, episodic, working = [], [], []
        for h in hits:
            oid = int(h["id"])
            row = rows.get(oid)
            body = parsed.get(oid, {}).get("preview", "")
            title = str(h.get("title", ""))
            if str(h.get("topic_key") or "").startswith("adebench-live/"):
                key, _, value = body.partition(": ")
                working.append({"key": key, "value": value})
            # an age only where the memory has a date of its own (it came
            # through import): mem_save's time is when it was written
            dated = row is not None and str(row["sync_id"]).startswith(IMPORTED)
            when = _day(row["created_at"]) if dated else ""
            if row is not None and row["prompts"]:
                # a session with the user's prompt: an episode, what was asked and what was done
                episodic.append({"created_at": _utc_iso(row["created_at"]), "input_summary": title,
                                 "output_summary": body, "_fallback": False})
            semantic.append({"source": f"engram:{h.get('type', 'manual')}", "key": oid,
                             "content": f"[since {when}] {title}: {body}" if when else f"{title}: {body}"})
        return {"summary": text, "semantic": semantic, "cards": [], "episodic": episodic,
                "working": working, "unknown_terms": [], "_raw": d or text}

    def _door(self, door: str | None) -> str:
        return door if door in DOORS else "search"

    def door_text(self, query: str, door: str) -> tuple[str, dict]:
        r = self._answer(query, self._door(door))
        text = competing_payload(CFG.pressure) + r["summary"]
        return (text[:self.cut] if self.cut else text), r

    def ask(self, query: str) -> dict:
        return self._answer(query, self._door(CFG.door))

    # ── cards, corrections, aliases: none ─────────────────────────────────
    def cards(self) -> list[dict]:
        return []

    def corrections(self) -> list[dict]:
        return []

    def aliases(self) -> list[dict]:
        return []

    # ── facts and their lifecycle ─────────────────────────────────────────
    def update_trace(self) -> dict:
        rel: dict[str, int] = {}
        for r in self._sql("SELECT relation, judgment_status, count(*) AS n FROM memory_relations GROUP BY 1, 2"):
            rel[f"{r['relation']}/{r['judgment_status']}"] = r["n"]
        live = self._sql("SELECT count(*) AS n FROM observations WHERE deleted_at IS NULL AND project = ?",
                         (self.project,))[0]["n"]
        revised = self._sql("SELECT count(*) AS n FROM observations WHERE deleted_at IS NULL AND project = ? "
                            "AND revision_count > 1", (self.project,))[0]["n"]
        return {"superseded_live": sum(n for k, n in rel.items() if k == "supersedes/judged"),
                "relations": rel, "observations_live": live, "topic_upserts": revised}

    def event_date_share(self) -> tuple[int, int]:
        # only what came in through import carries a date of its own; mem_save
        # stamps the write time, which is not the fact's date
        rows = self._sql("SELECT count(*) AS n, sum(sync_id LIKE ?) AS dated FROM observations "
                         "WHERE deleted_at IS NULL AND project = ?", (IMPORTED + "%", self.project))
        return (int(rows[0]["dated"] or 0), int(rows[0]["n"] or 0))

    # ── episodes and time: sessions with the user's prompt ────────────────
    def _episodes(self) -> list[sqlite3.Row]:
        return self._sql(
            "SELECT o.id, o.title, o.content, o.created_at FROM observations o "
            "WHERE o.deleted_at IS NULL AND o.project = ? "
            "AND EXISTS (SELECT 1 FROM user_prompts p WHERE p.session_id = o.session_id) "
            "ORDER BY o.created_at DESC", (self.project,))

    def recent_days(self, n: int) -> list[str]:
        days = {_day(r["created_at"]) for r in self._episodes()}
        return sorted((d for d in days if d), reverse=True)[:n]

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        return [{"created_at": _utc_iso(r["created_at"]), "input_summary": r["title"], "output_summary": r["content"]}
                for r in self._episodes() if _day(r["created_at"]) == day][:limit]

    def signed_episodes(self, prefix: str) -> int:
        return sum(1 for r in self._episodes() if str(r["title"]).startswith(prefix))

    # ── live state: one topic_key per key, upserted ───────────────────────
    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool:
        oid = self.save(key, f"{key}: {value}", topic_key=f"adebench-live/{session}/{key}")
        if oid:
            self._live[(session, key)] = oid
        return bool(oid)

    def working_read(self, session: str, key: str):
        oid = self._live.get((session, key))
        if not oid:
            return None
        rows = self._sql("SELECT content FROM observations WHERE id = ? AND deleted_at IS NULL", (oid,))
        if not rows:
            return None
        return str(rows[0]["content"]).split(": ", 1)[-1]

    def working_clear(self, session: str) -> None:
        for (s, _k), oid in list(self._live.items()):
            if s == session:
                self._delete(oid)
        self._live = {k: v for k, v in self._live.items() if k[0] != session}

    def working_age_minutes(self, session: str, key: str) -> float | None:
        oid = self._live.get((session, key))
        if not oid:
            return None
        rows = self._sql("SELECT updated_at FROM observations WHERE id = ? AND deleted_at IS NULL", (oid,))
        iso = _utc_iso(rows[0]["updated_at"]) if rows else ""
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds() / 60.0 if iso else None

    # ── files and graph: not exposed ──────────────────────────────────────
    def file_search(self, query: str, limit: int) -> list[str]:
        return []

    def graph_edges(self, entity: str) -> int:
        return 0

    def graph_orphans(self) -> tuple[int, int]:
        return (0, 0)

    def graph_counts(self) -> dict:
        return {}

    # ── report-only ───────────────────────────────────────────────────────
    def health_report(self) -> tuple[dict, list[str]]:
        measures: dict = {"tools_profile": TOOLS,
                          "fresh_store_required": "a run needs a fresh ENGRAM_DATA_DIR: deletes are soft and "
                                                  "the probes' conflict relations stay behind"}
        warnings = []
        try:
            row = self._sql("SELECT (SELECT count(*) FROM sessions) AS sessions, "
                            "(SELECT count(*) FROM observations WHERE deleted_at IS NULL) AS observations, "
                            "(SELECT count(*) FROM observations WHERE deleted_at IS NOT NULL) AS soft_deleted, "
                            "(SELECT count(*) FROM user_prompts) AS prompts")[0]
            measures.update({k: row[k] for k in row.keys()})
            measures.update(self.update_trace())
            pending = sum(n for k, n in measures["relations"].items() if k.endswith("/pending"))
            if pending:
                warnings.append(f"{pending} conflict relation(s) pending: Engram flags them on save for the "
                                "agent's model to judge (mem_judge); until then both memories are served")
        except EngramError as e:
            warnings.append(str(e)[:160])
        warnings.append("cards, files and entity graph do not exist in Engram: those sections are SKIP")
        return measures, warnings

    def measured_doors(self) -> list[str]:
        return ["mem_search any", "mem_search all"]

    def traces(self) -> list[dict]:
        return list(self._traces)

    def probe_doors(self, questions: list[str]) -> None:
        other = "search_all" if self._door(CFG.door) == "search" else "search"
        for q in questions:
            try:
                self._search(q, other)
            except EngramError:
                continue

    # ── optional ──────────────────────────────────────────────────────────
    def stored_mentions(self, phrase: str) -> int:
        like = f"%{phrase.lower()}%"
        rows = self._sql("SELECT (SELECT count(*) FROM observations WHERE deleted_at IS NULL "
                         "AND (lower(title) LIKE ? OR lower(content) LIKE ?)) "
                         "+ (SELECT count(*) FROM user_prompts WHERE lower(content) LIKE ?) AS n",
                         (like, like, like))
        return int(rows[0]["n"]) if rows else 0

    def _delete(self, oid: int) -> bool:
        # the agent profile has no mem_delete: Engram's CLI, a soft delete
        self._cli(["delete", str(int(oid))])
        rows = self._sql("SELECT deleted_at FROM observations WHERE id = ?", (int(oid),))
        return bool(rows and rows[0]["deleted_at"])

    def write_fact(self, text: str):
        # no name of an old fact: the title is Engram's own derivation from the text
        return self.save(title_of(text), text)

    def forget_memory(self, memory_id) -> bool:
        mid = str(memory_id)
        try:
            if mid.startswith("prompt:"):
                self._cli(["delete", "prompt", mid.split(":", 1)[1]])
                return True
            return self._delete(int(mid))
        except (EngramError, ValueError):
            return False

    def import_memory(self, text: str, written_at: str):
        rec = self.export_record(title_of(text), text, written_at, "adebench-import", self.project)
        self.import_export(self.export_file([rec]))
        return self._id_of(rec["observation"]["sync_id"])

    def ingest_exchange(self, question: str, answer: str):
        # what a client does after answering: the user's prompt, then the
        # observation of the answer, both in the same session
        session = f"adebench-exchange-{uuid.uuid4().hex[:8]}"
        # no directory: Engram would detect the project from it (a git root
        # above the data dir) instead of the measured one
        self._tool("mem_session_start", {"id": session})
        pid = self.save_prompt(question, session)
        oid = self.save(title_of(answer), answer, session=session)
        rows = self._sql("SELECT project FROM observations WHERE id = ?", (oid,)) if oid else []
        if rows and rows[0]["project"] != self.project:
            raise EngramError(f"the exchange was saved in project {rows[0]['project']!r}, not {self.project!r}")
        return [i for i in (oid, f"prompt:{pid}" if pid else None) if i]

    def declared_bytes(self) -> int | None:
        """tools/list of the server the door talks to: `engram mcp
        --tools=agent`, the profile `engram setup` installs (19 tools)."""
        try:
            tools = self._conn().tools
        except EngramError:
            return None
        return len(json.dumps([t.model_dump() for t in tools], separators=(",", ":")).encode("utf-8"))
