"""Adapter for Aionforge Memory (github.com/jscott3201/aionforge-memory): a
bi-temporal graph memory in Rust, reached over its MCP server.

Everything goes through the MCP surface, Streamable HTTP, the door an agent
has: `capture` to write (with the event's own time), `search` to read (a
bounded bundle of snippets, fused from lexical, vector, graph, recency and
trust signals), `forget`/`unforget`, `consolidate` (facts and entities derived
from episodes, deterministic, no model), `session_manifest` and
`memory_census` for the report. No Aionforge code is linked.

    docker run --network host ghcr.io/jscott3201/aionforge-memory:0.4.0 \\
        --config /config.toml serve http --listen 127.0.0.1:3918
    python examples/aionforge_import.py
    python -m adebench --adapter adebench.aionforge:AionforgeAdapter --cases examples/synthetic_data/cases

    AIONFORGE_URL        http://127.0.0.1:3918/mcp
    AIONFORGE_AGENT_ID   a fixed UUID: the agent whose private namespace is measured
    AIONFORGE_SESSION_ID a fixed UUID: the session the imported memory belongs to
    AIONFORGE_TOKEN      Bearer for a deployment with auth (empty for loopback)

Doors:
  search  what `search` returns for the question, the snippets in its order,
          each with the capture time; no cut (ADEBENCH_AIONFORGE_CUT=N)

What maps and what does not (SKIP is honest, not a zero):
  cards          none: entities exist as derived nodes, not as cards. Corrections,
                 aliases: none
  fact updates   `capture` takes an optional `supersedes` id, the client naming
                 what it replaces; the harness probe writes plain captures and
                 lets consolidation decide. write_fact/forget_memory: capture and
                 soft-forget
  time           captures carry `captured_at`; the day filter is done on
                 session_manifest, which lists a session's captures, in the
                 adapter (there is no day tool)
  live state     capture/search/forget, the memory verbs: no TTL, no live-state key
  files          not mapped: SKIP
  graph          graph signals shape recall but no tool exposes edges: SKIP
  declared bytes tools/list of the server, 45 KB for 23 tools
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time

from adebench.ade import competing_payload
from adebench.config import CFG

URL = os.environ.get("AIONFORGE_URL", "http://127.0.0.1:3918/mcp")
AGENT_ID = os.environ.get("AIONFORGE_AGENT_ID", "0b6f3f7e-5d5c-4e1a-9d3e-00000adeb001")
SESSION_ID = os.environ.get("AIONFORGE_SESSION_ID", "9c2a6b1e-1f2d-4c3b-8a4f-00000adeb002")
TOKEN = os.environ.get("AIONFORGE_TOKEN", "")
DOORS = ("search",)
_STOP = {"what", "which", "who", "when", "where", "does", "is", "the", "a", "an", "how", "many", "much",
         "about", "with", "for", "and", "that", "this", "are", "was", "were", "have", "has", "do", "did"}


class AionforgeError(RuntimeError):
    pass


class _Mcp:
    """One MCP session, kept open on a background event loop, driven from
    synchronous code. The mcp SDK is async; adebench is not."""

    def __init__(self, url: str, headers: dict) -> None:
        self.url, self.headers = url, headers
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.session = None
        self._stack = None
        self.tools: list = []
        self._run(self._open())

    def _run(self, coro, timeout: float = 300):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    async def _open(self):
        from contextlib import AsyncExitStack
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        self._stack = AsyncExitStack()
        r, w, _ = await self._stack.enter_async_context(streamablehttp_client(self.url, headers=self.headers))
        self.session = await self._stack.enter_async_context(ClientSession(r, w))
        await self.session.initialize()
        self.tools = (await self.session.list_tools()).tools

    async def _call(self, name: str, args: dict):
        res = await self.session.call_tool(name, args)
        text = "".join(c.text for c in res.content if hasattr(c, "text"))
        data = None
        if text.strip().startswith(("{", "[")):
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = None
        return {"text": text, "data": data, "error": bool(getattr(res, "isError", False)),
                "structured": getattr(res, "structuredContent", None)}

    def call(self, name: str, args: dict, timeout: float = 300) -> dict:
        return self._run(self._call(name, args), timeout)


class AionforgeAdapter:
    def __init__(self) -> None:
        self.url = URL
        self.agent = AGENT_ID
        self.session_id = SESSION_ID
        self.viewer = f"agent:{self.agent}"
        self.cut = int(os.environ.get("ADEBENCH_AIONFORGE_CUT", "0"))
        self.limit = int(os.environ.get("ADEBENCH_AIONFORGE_LIMIT", "10"))
        self._traces: list[dict] = []
        self._mcp: _Mcp | None = None
        self._live: dict[tuple[str, str], list[str]] = {}   # (session, key) -> memory ids

    # ── the MCP door ──────────────────────────────────────────────────────
    def _conn(self) -> _Mcp:
        if self._mcp is None:
            headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
            try:
                self._mcp = _Mcp(self.url, headers)
            except Exception as e:  # noqa: BLE001
                raise AionforgeError(f"cannot reach {self.url}: {type(e).__name__}: {e}") from e
        return self._mcp

    def _tool(self, name: str, args: dict, timeout: float = 300) -> dict:
        t0 = time.perf_counter()
        try:
            out = self._conn().call(name, args, timeout)
        except AionforgeError:
            raise
        except Exception as e:  # noqa: BLE001
            self._traces.append({"door": name, "ms": (time.perf_counter() - t0) * 1000, "chars": 0, "http": 500})
            raise AionforgeError(f"{name}: {type(e).__name__}: {e}") from e
        self._traces.append({"door": name, "ms": (time.perf_counter() - t0) * 1000,
                             "chars": len(out.get("text", "")), "http": 500 if out.get("error") else 200})
        if out.get("error"):
            raise AionforgeError(f"{name}: {out.get('text', '')[:200]}")
        return out

    @staticmethod
    def _payload(out: dict) -> dict:
        d = out.get("structured") or out.get("data")
        return d if isinstance(d, dict) else {}

    # ── writing ───────────────────────────────────────────────────────────
    def capture(self, text: str, when: str | None = None, role: str = "user",
                session: str | None = None, supersedes: str | None = None) -> str | None:
        args = {"agent_id": self.agent, "content": text, "role": role, "session_id": session or self.session_id}
        if when:
            # RFC3339 with a zone: "2021-03-14" and "2026-09-10T09:12:00" both need it
            ts = when if "T" in when else f"{when}T12:00:00"
            if not re.search(r"(Z|[+-]\d\d:\d\d)$", ts):
                ts += "Z"
            args["captured_at"] = ts
        if supersedes:
            args["supersedes"] = supersedes
        out = self._tool("capture", args)
        d = self._payload(out)
        for k in ("memory_id", "id", "episode_id"):
            if d.get(k):
                return str(d[k])
        # the receipt is text: "[capture] <uuid> verdict=new|duplicate ..."
        m = re.search(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", out.get("text", ""))
        self._dates_cache = None   # a new capture: the manifest is stale
        return m.group(0) if m else None

    def consolidate(self, ticks: int = 1) -> dict:
        try:
            return self._payload(self._tool("consolidate", {"max_ticks": ticks}, timeout=600))
        except AionforgeError as e:
            return {"error": str(e)[:200]}

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        try:
            out = self._tool("server_status", {}, timeout=60)
        except AionforgeError:
            return False
        return bool(out.get("text"))

    def warm_up(self) -> float | None:
        t0 = time.perf_counter()
        try:
            self._search("hello", 1)
        except AionforgeError:
            return None
        return (time.perf_counter() - t0) * 1000

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return list(DOORS)

    def door_cut(self, door: str) -> int | None:
        return self.cut or None

    def _search(self, query: str, limit: int | None = None) -> dict:
        return self._tool("search", {"query": query, "viewer": self.viewer, "limit": limit or self.limit,
                                     "verbose": True})

    @staticmethod
    def _hits(d: dict) -> list[dict]:
        for k in ("memories", "episodes", "hits", "results", "items", "matches"):
            v = d.get(k)
            if isinstance(v, list):
                return [h for h in v if isinstance(h, dict)]
        return []

    def _dates(self) -> dict[str, str]:
        """memory id -> captured_at, from the session manifest: a search hit
        carries no time, the manifest does."""
        if getattr(self, "_dates_cache", None) is None:
            self._dates_cache = {str(m.get("id")): str(m.get("captured_at") or "")[:10]
                                 for m in self._manifest() if m.get("id")}
        return self._dates_cache

    def _answer(self, query: str) -> dict:
        out = self._search(query)
        d = self._payload(out)
        semantic = []
        dates = self._dates()
        for h in self._hits(d):
            text = str(h.get("snippet") or h.get("content") or h.get("text") or h.get("body") or "").strip()
            if not text:
                continue
            when = str(h.get("captured_at") or h.get("event_time") or h.get("created_at")
                       or dates.get(str(h.get("id") or h.get("memory_id")), ""))[:10]
            kind = str(h.get("kind") or h.get("memory_kind") or "memory")
            semantic.append({"source": f"aionforge:{kind}", "key": h.get("memory_id") or h.get("id"),
                             "content": f"[since {when}] {text}" if re.match(r"\d{4}-\d{2}-\d{2}", when) else text,
                             "_score": h.get("score") or h.get("relevance")})
        # what the agent receives is the tool's text: the snippets, in its
        # order, inside <recalled-memory-context>. The lines above are the
        # same hits with their dates, for the checks that read them.
        # a live-state canary served by search is a working-memory entry
        live_ids = {m for ids in self._live.values() for m in ids}
        working = []
        for h, sem in zip(self._hits(d), semantic):
            if str(h.get("id")) in live_ids and ": " in sem["content"]:
                key, _, value = sem["content"].split("] ", 1)[-1].partition(": ")
                working.append({"key": key, "value": value})
        summary = "\n".join(s["content"] for s in semantic)
        # "hits: 0 of N considered": Aionforge found nothing it would serve.
        # That is its abstention, and the door passes it on as unknown terms.
        unknown = []
        if not semantic:
            unknown = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", query)
                       if w.lower() not in _STOP][:3]
            summary = out.get("text", "").split("<recalled-memory-context")[0].strip()
        return {"summary": summary, "semantic": semantic, "cards": [], "episodic": [],
                "working": working, "unknown_terms": unknown, "_raw": d or out.get("text", "")}

    def door_text(self, query: str, door: str) -> tuple[str, dict]:
        r = self._answer(query)
        text = competing_payload(CFG.pressure) + r["summary"]
        return (text[:self.cut] if self.cut else text), r

    def ask(self, query: str) -> dict:
        return self._answer(query)

    # ── cards, corrections, aliases: none ─────────────────────────────────
    def cards(self) -> list[dict]:
        return []

    def corrections(self) -> list[dict]:
        return []

    def aliases(self) -> list[dict]:
        return []

    # ── facts and their lifecycle ─────────────────────────────────────────
    def _census(self, mode: str = "counts", kind: str | None = None, limit: int = 200) -> dict:
        args = {"viewer": self.viewer, "mode": mode, "limit": limit}
        if kind:
            args["kind"] = kind
        return self._payload(self._tool("memory_census", args))

    def update_trace(self) -> dict:
        c = self._census()
        counts = c.get("counts") or c.get("namespaces") or c
        return {"census": counts if isinstance(counts, (dict, list)) else {},
                "superseded_live": int(c.get("superseded") or 0) if isinstance(c, dict) else 0}

    def _manifest(self) -> list[dict]:
        out: list[dict] = []
        after = None
        for _ in range(10):
            args = {"session_id": self.session_id, "viewer": self.viewer, "limit": 200, "verbose": True}
            if after:
                args["after"] = after
            d = self._payload(self._tool("session_manifest", args))
            items = self._hits(d)
            out.extend(items)
            after = d.get("next") or d.get("cursor")
            if not after or not items:
                break
        return out

    def event_date_share(self) -> tuple[int, int]:
        items = self._manifest()
        dated = sum(1 for m in items if re.match(r"\d{4}-\d{2}-\d{2}", str(m.get("captured_at") or "")))
        return (dated, len(items))

    # ── episodes and time ─────────────────────────────────────────────────
    @staticmethod
    def _day(m: dict) -> str:
        return str(m.get("captured_at") or m.get("created_at") or "")[:10]

    def recent_days(self, n: int) -> list[str]:
        days = {self._day(m) for m in self._manifest()}
        return sorted((d for d in days if d), reverse=True)[:n]

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        out = []
        for m in self._manifest():
            if self._day(m) == day:
                text = str(m.get("snippet") or m.get("content") or m.get("text") or "")
                out.append({"created_at": str(m.get("captured_at") or ""), "input_summary": text,
                            "output_summary": ""})
        return out[:limit]

    def signed_episodes(self, prefix: str) -> int:
        return sum(1 for m in self._manifest()
                   if str(m.get("snippet") or m.get("content") or "").startswith(prefix))

    # ── live state: capture / search / forget ─────────────────────────────
    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool:
        for mid in self._live.pop((session, key), []):
            self._forget(mid)
        # role user, not event: search serves user/assistant captures
        mid = self.capture(f"{key}: {value}", role="user", session=self.session_id)
        if mid and mid in {m for ids in self._live.values() for m in ids}:
            return False   # deduplicated onto a live canary: the write did not happen
        if mid:
            self._live[(session, key)] = [mid]
        return bool(mid)

    def working_read(self, session: str, key: str):
        ids = self._live.get((session, key))
        if not ids:
            return None
        d = self._payload(self._tool("read_memory", {"memory_ids": ids, "viewer": self.viewer, "full": True}))
        for h in self._hits(d):
            text = str(h.get("body") or h.get("content") or h.get("snippet") or h.get("text") or "")
            if text:
                return text.split(":", 1)[1].strip() if ":" in text else text
        return None

    def working_clear(self, session: str) -> None:
        for (s, _k), ids in list(self._live.items()):
            if s == session:
                for mid in ids:
                    self._forget(mid)
        self._live = {k: v for k, v in self._live.items() if k[0] != session}

    def working_age_minutes(self, session: str, key: str) -> float | None:
        return None

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
        measures, warnings = {}, []
        try:
            measures["status"] = self._payload(self._tool("server_status", {"verbose": False}, timeout=60))
        except AionforgeError as e:
            warnings.append(str(e)[:120])
        try:
            measures["consolidation"] = self._payload(self._tool("consolidation_status", {}, timeout=60))
        except AionforgeError:
            pass
        warnings.append("cards, files and graph edges are not exposed by the MCP surface: those sections are SKIP")
        return measures, warnings

    def measured_doors(self) -> list[str]:
        return ["search"]

    def traces(self) -> list[dict]:
        return list(self._traces)

    def probe_doors(self, questions: list[str]) -> None:
        return None

    # ── optional ──────────────────────────────────────────────────────────
    def stored_mentions(self, phrase: str) -> int:
        low = phrase.lower()
        d = self._payload(self._search(phrase, 20))
        return sum(1 for h in self._hits(d)
                   if low in str(h.get("snippet") or h.get("content") or "").lower())

    def _forget(self, memory_id: str) -> bool:
        try:
            out = self._tool("forget", {"memory_id": memory_id, "viewer": self.viewer})
        except AionforgeError:
            return False
        d = self._payload(out)
        txt = out.get("text", "").lower()
        # "[forget] <id> ... outcome=forgotten" | "outcome=protected(ImportanceHolds)"
        # | "outcome=disabled": only the first is a removal
        return bool(d.get("forgotten")) or "outcome=forgotten" in txt

    def write_fact(self, text: str):
        return self.capture(text)

    def settle(self) -> None:
        self.consolidate(1)

    def forget_memory(self, memory_id: str) -> bool:
        return self._forget(memory_id)

    def import_memory(self, text: str, written_at: str):
        return self.capture(text, when=written_at)

    def ingest_exchange(self, question: str, answer: str):
        ids = [self.capture(question, role="user"), self.capture(answer, role="assistant")]
        return [i for i in ids if i]

    def declared_bytes(self) -> int | None:
        try:
            tools = self._conn().tools
        except AionforgeError:
            return None
        return len(json.dumps([t.model_dump() for t in tools], separators=(",", ":")).encode("utf-8"))
