"""Adapter for TokenMizer (github.com/Shweta-Mishra-ai/tokenmizer): session
memory for coding agents, reached through its own HTTP API.

TokenMizer is an OpenAI-compatible proxy: the conversation passes through it,
an extractor turns it into a graph of tasks, decisions, files, errors and
goals, and `resume` replays that graph in a few hundred tokens when the
context runs out. Its node types are those of a software session; there is no
node for "the owner prefers the report as a bullet list", and no query over
the graph other than `why` (the causal chain behind a decision). This adapter
measures it as it is, through the surface an agent has: the proxy to write,
`resume` and `why` to read.

    pip install tokenmizer
    tokenmizer serve --config tokenmizer.yaml     # use_llm_extraction: true
    python examples/tokenmizer_import.py          # the synthetic memory, through the proxy
    python -m adebench --adapter adebench.tokenmizer:TokenmizerAdapter \\
        --cases sets/quick/cases --sections door cards updates time abstention graph census doors

    TOKENMIZER_URL          http://127.0.0.1:8000
    TOKENMIZER_SESSION      adebench            the session whose graph is measured
    TOKENMIZER_MODEL        (the proxy's default_model) the upstream model the proxy calls on a write
    TOKENMIZER_API_KEY      (empty)             the proxy's own Bearer, when it has one
    TOKENMIZER_MCP          (tokenmizer-mcp on PATH) the MCP server whose why_decision text is read

Doors (both are text a client literally receives; nothing is re-rendered):
  resume  the `resume_context` of `GET /api/resume/{session}?level=full` (read
          from the live graph), then the text of the MCP tool `why_decision`
          for the question: what an agent gets when it picks the session up and
          asks about one thing. The resume block does not change with the
          question; `why` does. No cut (ADEBENCH_TOKENMIZER_CUT=N)
  why     the text of `why_decision` alone (tokenmizer-mcp over stdio): the
          only query TokenMizer answers, the supersession chain of a decision.
          Nodes carry `first_seen`, the time they were stored: it is never shown
          as an age

What maps and what does not (SKIP is honest, not a zero):
  cards          none. Corrections, aliases: none
  fact updates   decisions superseding decisions, read from `transitions`; the
                 harness probe runs through write_fact (a turn through the
                 proxy) and forget_memory (`/api/decision/invalidate`)
  time           nodes carry `first_seen`; no episodes, no day filter: SKIP
  live state     none. Run without the live_state section
  files          file nodes come from paths named in the conversation, not from
                 a repository: SKIP
  graph          the whole point: nodes and edges from `viz`
  declared bytes `tokenmizer-mcp` over stdio, its tools/list

Every write goes through the proxy, which calls the upstream model: a write
costs one model call and the extraction another. The graph is a scratch
session; `TOKENMIZER_SESSION` should not be one a person uses.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from adebench.ade import competing_payload
from adebench.config import CFG

URL = os.environ.get("TOKENMIZER_URL", "http://127.0.0.1:8000").rstrip("/")
SESSION = os.environ.get("TOKENMIZER_SESSION", "adebench")
DOORS = ("resume", "why")
RETRIES = 5   # a 429 from TokenMizer's rate limiter is retried after the wait it names
STOP = {"the", "what", "which", "who", "how", "does", "do", "is", "are", "for", "and", "with", "about",
        "when", "where", "of", "on", "in", "a", "an", "to", "was", "were", "did", "has", "have", "it", "its"}


class TokenmizerError(RuntimeError):
    pass


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9][a-z0-9._-]{2,}", (text or "").lower()) if w not in STOP}


class TokenmizerAdapter:
    def __init__(self) -> None:
        self.url = URL
        self.session = SESSION
        self.model = os.environ.get("TOKENMIZER_MODEL", "")
        self.key = os.environ.get("TOKENMIZER_API_KEY", "")
        self.cut = int(os.environ.get("ADEBENCH_TOKENMIZER_CUT", "0"))
        self._traces: list[dict] = []
        self._written: dict[str, str] = {}   # write_fact id -> text, for forget_memory

    # ── the HTTP door ─────────────────────────────────────────────────────
    def _http(self, method: str, path: str, body: dict | None = None, query: dict | None = None,
              timeout: float = 300) -> dict:
        url = self.url + path
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        # TokenMizer's own rate limiter answers 429 "Retry after Xs": wait and ask again, as a
        # client would (at most RETRIES times); the time spent waiting is not the door's latency
        for attempt in range(RETRIES + 1):
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    raw, http = r.read().decode("utf-8", "replace"), r.status
            except urllib.error.HTTPError as e:
                raw, http = e.read().decode("utf-8", "replace"), e.code
            except OSError as e:
                raise TokenmizerError(f"{method} {path}: {type(e).__name__}: {e}") from e
            if http != 429 or attempt == RETRIES:
                break
            wait = re.search(r"[Rr]etry after ([0-9.]+)", raw)
            time.sleep(min(max(float(wait.group(1)) if wait else 1.0, 0.1), 10.0))
        self._traces.append({"door": path.split("/")[2] if path.count("/") > 1 else path,
                             "ms": (time.perf_counter() - t0) * 1000, "chars": len(raw), "http": http})
        if http == 404:
            return {}
        if http >= 400:
            raise TokenmizerError(f"{method} {path}: HTTP {http}: {raw[:200]}")
        try:
            out = json.loads(raw)
        except json.JSONDecodeError as e:
            raise TokenmizerError(f"{method} {path}: not JSON: {raw[:120]}") from e
        return out if isinstance(out, dict) else {"result": out}

    def _viz(self) -> dict:
        v = self._http("GET", f"/api/graph/{self.session}/viz")
        return v if isinstance(v, dict) else {}

    def _nodes(self) -> list[dict]:
        return [n for n in self._viz().get("nodes", []) if isinstance(n, dict)]

    # ── writing: a turn through the proxy ─────────────────────────────────
    def chat(self, text: str, system: str = "You are the assistant of a small company. "
             "Acknowledge the facts you are told in one short sentence.") -> dict:
        """One exchange through the proxy, the way TokenMizer learns anything:
        the upstream model answers, and the extractor reads both turns."""
        body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": text}],
                "session_id": self.session}
        if self.model:
            body["model"] = self.model
        return self._http("POST", "/v1/chat/completions", body, timeout=600)

    def settle(self) -> None:
        """The LLM extraction runs in the background after the answer: give it
        time before the door is asked (ADEBENCH_TOKENMIZER_SETTLE_S, default 8)."""
        time.sleep(float(os.environ.get("ADEBENCH_TOKENMIZER_SETTLE_S", "8")))

    def checkpoint(self) -> dict:
        return self._http("POST", "/api/checkpoint", query={"session_id": self.session})

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        try:
            h = self._http("GET", "/health", timeout=30)
        except TokenmizerError:
            return False
        return str(h.get("status", "")).lower() in ("ok", "healthy")

    def warm_up(self) -> float | None:
        t0 = time.perf_counter()
        try:
            self._viz()
        except TokenmizerError:
            return None
        return (time.perf_counter() - t0) * 1000

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return list(DOORS)

    def door_cut(self, door: str) -> int | None:
        return self.cut or None

    def _why(self, query: str) -> dict:
        return self._http("GET", f"/api/graph/{self.session}/why", query={"q": query})

    def _resume(self) -> str:
        r = self._http("GET", f"/api/resume/{self.session}", query={"level": "full"})
        if not r:
            # nothing checkpointed yet: make one, as the CLI and the skill do
            self.checkpoint()
            r = self._http("GET", f"/api/resume/{self.session}", query={"level": "full"})
        return str(r.get("resume_context") or "")

    def _mcp(self, requests: list[dict], want_id: int, timeout: float = 120) -> dict | None:
        """One short tokenmizer-mcp session over stdio: initialize, then the
        given requests; returns the result of the one with id want_id."""
        exe = os.environ.get("TOKENMIZER_MCP") or shutil.which("tokenmizer-mcp")
        if not exe:
            return None
        req = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "adebench", "version": "0"}}},
               {"jsonrpc": "2.0", "method": "notifications/initialized"}] + requests
        try:
            p = subprocess.run([exe], capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                               errors="replace", input="\n".join(json.dumps(m) for m in req) + "\n",
                               env={**os.environ, "TOKENMIZER_URL": self.url})
        except (OSError, subprocess.TimeoutExpired):
            return None
        for line in (p.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("id") == want_id and isinstance(msg.get("result"), dict):
                    return msg["result"]
        return None

    def _why_text(self, query: str) -> str:
        """The literal text an agent gets from the MCP tool why_decision."""
        r = self._mcp([{"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "why_decision",
                                   "arguments": {"session_id": self.session, "query": query}}}], 3)
        if r is None:
            raise TokenmizerError("tokenmizer-mcp not found or not answering: set TOKENMIZER_MCP")
        return "\n".join(c.get("text", "") for c in (r.get("content") or []) if isinstance(c, dict)).strip()

    def _answer(self, query: str, door: str) -> dict:
        # the door delivers literal text; the JSON of the same query only tells
        # the harness which decisions were matched (for abstention). first_seen
        # is the time a node was stored, never shown as an age
        why = self._why(query)
        semantic = []
        for m in (why.get("matches") or []) + (why.get("chain") or []):
            if not isinstance(m, dict):
                continue
            text = str(m.get("label") or m.get("to_label") or m.get("to") or m.get("text") or "").strip()
            if text:
                semantic.append({"source": "tokenmizer:why", "key": m.get("id"), "content": text})
        parts = []
        if door == "resume":
            resume = self._resume()
            if resume:
                parts.append(resume)
        parts.append(self._why_text(query))
        return {"summary": "\n\n".join(p for p in parts if p), "semantic": semantic, "cards": [],
                "episodic": [], "working": [], "unknown_terms": [], "_raw": why}

    def door_text(self, query: str, door: str) -> tuple[str, dict]:
        r = self._answer(query, door)
        text = competing_payload(CFG.pressure) + r["summary"]
        return (text[:self.cut] if self.cut else text), r

    def ask(self, query: str) -> dict:
        return self._answer(query, CFG.door if CFG.door in DOORS else "resume")

    # ── cards, corrections, aliases: none ─────────────────────────────────
    def cards(self) -> list[dict]:
        return []

    def corrections(self) -> list[dict]:
        return []

    def aliases(self) -> list[dict]:
        return []

    # ── facts and their lifecycle ─────────────────────────────────────────
    def update_trace(self) -> dict:
        nodes = self._nodes()
        by_status: dict[str, int] = {}
        for n in nodes:
            by_status[str(n.get("status"))] = by_status.get(str(n.get("status")), 0) + 1
        tr = self._http("GET", f"/api/graph/{self.session}/transitions")
        transitions = tr.get("transitions") if isinstance(tr, dict) else None
        if transitions is None and isinstance(tr, dict):
            transitions = tr.get("result")
        return {"superseded_live": by_status.get("superseded", 0),
                "relation_updates": len(transitions) if isinstance(transitions, list) else 0,
                "archive_by_reason": by_status}

    def event_date_share(self) -> tuple[int, int]:
        # first_seen is when a node was stored, not when the fact happened:
        # no node carries the date of its fact
        return (0, len(self._nodes()))

    # ── episodes and time: none ───────────────────────────────────────────
    def recent_days(self, n: int) -> list[str]:
        return []

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        return []

    def signed_episodes(self, prefix: str) -> int:
        return 0

    # ── live state: none ──────────────────────────────────────────────────
    def working_write(self, session: str, key: str, value: str, ttl_hours: int):
        return None

    def working_read(self, session: str, key: str):
        return None

    def working_clear(self, session: str) -> None:
        return None

    def working_age_minutes(self, session: str, key: str) -> float | None:
        return None

    # ── files and graph ───────────────────────────────────────────────────
    def file_search(self, query: str, limit: int) -> list[str]:
        return []

    def graph_edges(self, entity: str) -> int:
        v = self._viz()
        ent = entity.lower().replace("_", " ")
        ids = {n.get("id") for n in v.get("nodes", []) if isinstance(n, dict)
               and ent in str(n.get("label", "")).lower().replace("_", " ")}
        return sum(1 for e in v.get("edges", []) if isinstance(e, dict)
                   and (e.get("source") in ids or e.get("target") in ids))

    def graph_orphans(self) -> tuple[int, int]:
        v = self._viz()
        nodes = [n for n in v.get("nodes", []) if isinstance(n, dict)]
        linked = set()
        for e in v.get("edges", []):
            if isinstance(e, dict):
                linked.add(e.get("source")); linked.add(e.get("target"))
        return (sum(1 for n in nodes if n.get("id") not in linked), len(nodes))

    def graph_counts(self) -> dict:
        v = self._viz()
        return {"nodes": len(v.get("nodes", [])), "edges": len(v.get("edges", []))}

    # ── report-only ───────────────────────────────────────────────────────
    def health_report(self) -> tuple[dict, list[str]]:
        measures, warnings = {}, []
        nodes = self._nodes()
        by_type: dict[str, int] = {}
        for n in nodes:
            by_type[str(n.get("type"))] = by_type.get(str(n.get("type")), 0) + 1
        measures["nodes_by_type"] = by_type
        try:
            st = self._http("GET", "/api/stats", timeout=30)
            for k in ("llm_extraction_failures", "silent_failures"):
                if k in st:
                    measures[k] = st[k]
        except TokenmizerError:
            pass
        warnings.append("node types are those of a software session (task, decision, file, error, goal): "
                        "a fact about a person has no node to become")
        return measures, warnings

    def measured_doors(self) -> list[str]:
        return ["why", "resume"]

    def traces(self) -> list[dict]:
        return list(self._traces)

    def probe_doors(self, questions: list[str]) -> None:
        for q in questions[:2]:
            try:
                self._why(q)
            except TokenmizerError:
                continue

    # ── optional ──────────────────────────────────────────────────────────
    def stored_mentions(self, phrase: str) -> int:
        low = phrase.lower()
        return sum(1 for n in self._nodes() if low in str(n.get("label", "")).lower())

    def write_fact(self, text: str):
        """Teach the memory one fact the normal way: a turn through the proxy.
        Whether it becomes a node, and which node, is the extractor's."""
        self.chat(text)
        self.settle()
        fid = f"turn:{len(self._written) + 1}"
        self._written[fid] = text
        return fid

    def forget_memory(self, memory_id: str) -> bool:
        """The only removal TokenMizer offers is invalidating a decision by
        label. The nodes the turn produced are looked up by the words of the
        text; a node that is not a decision cannot be removed, and the report
        says the removal was not confirmed."""
        text = self._written.pop(memory_id, "")
        if not text:
            return False
        words = _words(text)
        ok = False
        for n in self._nodes():
            if len(words & _words(str(n.get("label", "")))) >= 2:
                try:
                    r = self._http("POST", "/api/decision/invalidate",
                                   {"session_id": self.session, "decision": n.get("label"), "reason": "adebench probe"})
                    ok = ok or bool(r.get("ok", r.get("success", r.get("invalidated"))))
                except TokenmizerError:
                    continue
        return ok

    def declared_bytes(self) -> int | None:
        """What tokenmizer-mcp puts in an agent's context: its tools/list."""
        exe = os.environ.get("TOKENMIZER_MCP") or shutil.which("tokenmizer-mcp")
        if not exe:
            return None
        req = [{"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "adebench", "version": "0"}}},
               {"jsonrpc": "2.0", "method": "notifications/initialized"},
               {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}]
        try:
            p = subprocess.run([exe], capture_output=True, text=True, timeout=60, encoding="utf-8",
                               errors="replace", input="\n".join(json.dumps(m) for m in req) + "\n",
                               env={**os.environ, "TOKENMIZER_URL": self.url})
        except (OSError, subprocess.TimeoutExpired):
            return None
        for line in (p.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("{"):
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("id") == 2 and isinstance(msg.get("result"), dict):
                    return len(json.dumps(msg["result"], separators=(",", ":")).encode("utf-8"))
        return None
