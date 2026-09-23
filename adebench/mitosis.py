"""Adapter for Mitosis Cortex (mitosislabs.ai): a memory reached over MCP.

Everything goes through the door Cortex gives an agent: its remote MCP
server, Streamable HTTP, called with plain JSON-RPC. No Mitosis code is
imported and no private endpoint is used — the tools here are the ones the
server itself declares in tools/list.

    MITOSIS_TOKEN=... python -m adebench --adapter adebench.mitosis:MitosisAdapter \\
        --cases my/cases --sections door cards time abstention file_search census doors

Doors:
  ask     what an agent gets from `cortex_ask`: the fused vector, full-text
          and graph answer with its citations, the door Mitosis tells agents
          to prefer; no cut (ADEBENCH_MITOSIS_CUT=N cuts it at N characters,
          to compare with a memory whose client has a budget, e.g. 2400)
  recall  `cortex_recall`, semantic-only vector search over the same memory:
          the same question through the narrower door, so the report shows
          what the fusion adds

What maps and what does not (SKIP is honest, not a zero):
  cards          Cortex has no entity cards to read as such; corrections and
                 aliases: none. Those cases SKIP
  fact updates   no supersede trace is exposed; the section needs write_fact
                 (see below) or a sandbox test you point to
  time           facts carry the freshness Cortex returns with a citation;
                 `since` / `until` on cortex_ask bound a day, but there is no
                 episode list to filter, so the day cases SKIP
  live state     NOT RUN by default: writing a canary is easy
                 (cortex_remember), removing it afterwards is not — the
                 server declares no delete tool. adebench writes into a
                 memory only when it can clean up, so the live_state section
                 stays out of the run (see --sections above)
  files          cortex_ask restricted to a file source table
                 (ADEBENCH_MITOSIS_FILE_SOURCE, e.g. drive_files)
  graph          the graph is used at retrieval but not readable: SKIP
  declared bytes the server's own tools/list, measured byte for byte

Why the write probes are off: import_memory, ingest_exchange and write_fact
all write into the memory they measure, and adebench runs them only with a
way to remove what was written. Cortex declares cortex_remember, cortex_ingest
and cortex_ingest_conversation, and no delete. The day a forget tool exists,
write_fact is three lines here and the updates probe runs like anywhere else.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from adebench.ade import competing_payload
from adebench.config import CFG

URL = os.environ.get("MITOSIS_MCP_URL", "https://mitosislabs.ai/api/mcp")
TOKEN = os.environ.get("MITOSIS_TOKEN", "")
DOORS = ("ask", "recall")
PROTOCOL = "2025-11-25"


class MitosisError(RuntimeError):
    pass


class MitosisAdapter:
    def __init__(self) -> None:
        self.url = URL
        self.token = TOKEN
        self.cut = int(os.environ.get("ADEBENCH_MITOSIS_CUT", "0"))
        self.limit = int(os.environ.get("ADEBENCH_MITOSIS_LIMIT", "10"))
        self.file_source = os.environ.get("ADEBENCH_MITOSIS_FILE_SOURCE", "")
        self._traces: list[dict] = []
        self._session: str | None = None
        self._tools_bytes: int | None = None

    # ── the MCP door ──────────────────────────────────────────────────────
    def _rpc(self, method: str, params: dict | None = None, timeout: float = 120):
        """One JSON-RPC call to the MCP server. Streamable HTTP answers with
        JSON or with an SSE stream; both carry the same envelope."""
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                           "params": params or {}}).encode("utf-8")
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PROTOCOL}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self._session:
            headers["Mcp-Session-Id"] = self._session
        req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", "replace")
                sid = r.headers.get("Mcp-Session-Id")
                http = r.status
        except urllib.error.HTTPError as e:
            raw, sid, http = e.read().decode("utf-8", "replace"), None, e.code
        except OSError as e:
            raise MitosisError(f"{method}: {type(e).__name__}: {e}") from e
        ms = (time.perf_counter() - t0) * 1000
        self._traces.append({"door": params.get("name", method) if params else method,
                             "ms": ms, "chars": len(raw), "http": http})
        if sid:
            self._session = sid
        if http >= 400:
            raise MitosisError(f"{method}: HTTP {http}: {raw[:200]}")
        env = self._envelope(raw)
        if not isinstance(env, dict):
            raise MitosisError(f"{method}: no JSON-RPC envelope in {raw[:200]}")
        if env.get("error"):
            raise MitosisError(f"{method}: {json.dumps(env['error'])[:200]}")
        return env.get("result", {})

    @staticmethod
    def _envelope(raw: str):
        """The JSON-RPC envelope, from a JSON body or from the SSE stream the
        same endpoint may answer with (`data: {...}` lines)."""
        text = raw.strip()
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
        for line in reversed(text.split("\n")):
            line = line.strip()
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
        return None

    def _handshake(self) -> None:
        if self._session is not None:
            return
        self._session = ""     # one attempt only: a server without sessions is fine
        from adebench import __version__
        self._rpc("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                 "clientInfo": {"name": "adebench", "version": __version__}})

    def _tool(self, name: str, args: dict | None = None, timeout: float = 120) -> dict:
        self._handshake()
        res = self._rpc("tools/call", {"name": name, "arguments": args or {}}, timeout)
        if not isinstance(res, dict):
            return {}
        if res.get("structuredContent"):
            return res["structuredContent"]
        # else the result is content blocks: JSON when the tool returns data,
        # text when it returns prose. Both are what the agent receives.
        parts, data = [], None
        for block in res.get("content", []) if isinstance(res.get("content"), list) else []:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        joined = "\n".join(parts).strip()
        if joined.startswith(("{", "[")):
            try:
                data = json.loads(joined)
            except json.JSONDecodeError:
                data = None
        if isinstance(data, dict):
            return data
        return {"text": joined, "items": data if isinstance(data, list) else []}

    # ── what a Cortex answer contains ─────────────────────────────────────
    @staticmethod
    def _hits(res: dict) -> list[dict]:
        for key in ("results", "citations", "memories", "hits", "items", "matches"):
            v = res.get(key)
            if isinstance(v, list) and v:
                return [h for h in v if isinstance(h, dict)]
        return []

    @staticmethod
    def _hit_text(h: dict) -> str:
        for key in ("text", "excerpt", "content", "snippet", "summary", "body"):
            v = h.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""

    @staticmethod
    def _hit_date(h: dict) -> str:
        for key in ("freshness", "occurred_at", "created_at", "date", "timestamp", "updated_at"):
            v = h.get(key)
            if isinstance(v, str) and re.match(r"\d{4}-\d{2}-\d{2}", v):
                return v[:10]
        return ""

    def _answer(self, query: str, door: str) -> dict:
        """The raw answer of one door, as the adapter contract describes it:
        the composed text plus the citations, each dated with the freshness
        Cortex returns, so the time section can read an age."""
        if door == "recall":
            res = self._tool("cortex_recall", {"query": query, "limit": self.limit})
        else:
            res = self._tool("cortex_ask", {"question": query, "limit": self.limit})
        hits = self._hits(res)
        semantic = []
        for h in hits:
            text = self._hit_text(h)
            if not text:
                continue
            date = self._hit_date(h)
            semantic.append({"source": "cortex:" + str(h.get("source_table") or h.get("source") or "memory"),
                             "content": f"[since {date}] {text}" if date else text})
        summary = res.get("answer") or res.get("summary") or res.get("text") or ""
        if not summary:
            summary = "\n".join(s["content"] for s in semantic)
        unknown = []
        if res.get("source_gap") or res.get("possible_source_gap"):
            # Cortex says it: the memory has no connected source for this
            # question. That is an abstention, not an empty answer.
            unknown = [w for w in re.findall(r"[A-Za-zÀ-ÿ']{3,}", query)][:3]
        return {"summary": str(summary), "semantic": semantic, "cards": [], "episodic": [],
                "working": [], "unknown_terms": unknown, "_raw": res}

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        try:
            res = self._tool("cortex_status", timeout=60)
        except MitosisError:
            return False
        if not isinstance(res, dict) or not res:
            return False
        status = str(res.get("status") or res.get("state") or "").lower()
        return status in ("", "ok", "healthy", "up", "ready") and not res.get("error")

    def warm_up(self) -> float | None:
        try:
            t0 = time.perf_counter()
            self._tool("cortex_recall", {"query": "hello", "limit": 1}, timeout=120)
            return (time.perf_counter() - t0) * 1000
        except MitosisError:
            return None

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return list(DOORS)

    def door_cut(self, door: str) -> int | None:
        return self.cut or None

    def door_text(self, query: str, door: str) -> tuple[str, dict]:
        r = self._answer(query, door)
        text = competing_payload(CFG.pressure) + r["summary"]
        if not r["summary"] and r["semantic"]:
            text = competing_payload(CFG.pressure) + "\n".join(s["content"] for s in r["semantic"])
        return (text[:self.cut] if self.cut else text), r

    def ask(self, query: str) -> dict:
        return self._answer(query, CFG.door if CFG.door in DOORS else "ask")

    # ── cards, corrections, aliases: Cortex has none to read ──────────────
    def cards(self) -> list[dict]:
        return []

    def corrections(self) -> list[dict]:
        return []

    def aliases(self) -> list[dict]:
        return []

    # ── facts and their lifecycle ─────────────────────────────────────────
    def update_trace(self) -> dict:
        return {}

    def event_date_share(self) -> tuple[int, int]:
        return (0, 0)

    # ── episodes and time ─────────────────────────────────────────────────
    def recent_days(self, n: int) -> list[str]:
        return []

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        return []

    def signed_episodes(self, prefix: str) -> int:
        return 0

    # ── live state: not run, nothing here writes ──────────────────────────
    def working_write(self, session: str, key: str, value: str, ttl_hours: int):
        """None, not False: the canary is not written. Cortex can store one
        (cortex_remember) but declares no way to remove it, and adebench does
        not leave behind what it writes. Run without the live_state section."""
        return None

    def working_read(self, session: str, key: str):
        return None

    def working_clear(self, session: str) -> None:
        return None

    def working_age_minutes(self, session: str, key: str) -> float | None:
        return None

    # ── files and graph ───────────────────────────────────────────────────
    def file_search(self, query: str, limit: int) -> list[str]:
        if not self.file_source:
            return []
        res = self._tool("cortex_ask", {"question": query, "limit": limit,
                                        "source_table": self.file_source})
        paths = []
        for h in self._hits(res):
            p = h.get("path") or h.get("filename") or h.get("title") or h.get("name")
            if isinstance(p, str) and p.strip():
                paths.append(p.strip())
        return paths[:limit]

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
            m = self._tool("cortex_manifest", timeout=60)
            if isinstance(m, dict):
                for k in ("sources", "feeds", "counts", "connected_sources"):
                    if k in m:
                        measures[k] = m[k] if not isinstance(m[k], list) else len(m[k])
        except MitosisError as e:
            warnings.append(f"cortex_manifest: {e}")
        warnings.append("no delete tool declared: the write probes (updates, write-back, "
                        "imported date) do not run on this memory")
        return measures, warnings

    def measured_doors(self) -> list[str]:
        return ["cortex_ask", "cortex_recall"]

    def traces(self) -> list[dict]:
        return list(self._traces)

    def probe_doors(self, questions: list[str]) -> None:
        for q in questions[:2]:
            try:
                self._tool("cortex_recall", {"query": q, "limit": self.limit})
            except MitosisError:
                continue

    # ── optional ──────────────────────────────────────────────────────────
    def stored_mentions(self, phrase: str) -> int:
        """How many stored items contain the phrase, read through the door:
        the abstention section uses it to warn when an invented entity of the
        golden set is already in the memory."""
        try:
            res = self._tool("cortex_recall", {"query": phrase, "limit": 20})
        except MitosisError:
            return 0
        low = phrase.lower()
        return sum(1 for h in self._hits(res) if low in self._hit_text(h).lower())

    def declared_bytes(self) -> int | None:
        """What the Cortex MCP server puts in every agent's context before a
        question is even asked: its own tools/list, measured byte for byte."""
        if self._tools_bytes is None:
            try:
                self._handshake()
                res = self._rpc("tools/list", {})
                self._tools_bytes = len(json.dumps(res, separators=(",", ":")).encode("utf-8"))
            except MitosisError:
                return None
        return self._tools_bytes
