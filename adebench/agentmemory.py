"""Adapter for agentmemory (github.com/rohitg00/agentmemory): local-first
memory for coding agents in TypeScript on the iii engine, reached over its
REST API (the same routes its MCP shim forwards to).

Everything goes through the REST surface with urllib, no agentmemory code is
linked. The door is the MCP tool itself, called through the route the stdio
shim forwards to (POST /agentmemory/mcp/call): `memory_recall` (BM25 fused
with local vectors, the full observations) and `memory_smart_search` (the
compact list the recall skill starts from). Writes are `memory_save`'s route
(/remember), the dated export/import (/import) and the transcript import
(/replay/import-jsonl); `forget` removes; /export, /memories, /timeline and
/health feed the rest.

    npm install @agentmemory/agentmemory@0.9.29      # plus iii-engine 0.11.2 (iii.exe on Windows)
    EMBEDDING_PROVIDER=local agentmemory             # keyless: provider noop, all-MiniLM-L6-v2 on this machine
    python examples/agentmemory_import.py
    ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.agentmemory:AgentmemoryAdapter \\
        --cases examples/synthetic_data/cases --history /tmp/agentmemory-run --write-back

Two modes of use, the same adapter unchanged (it reads the mode from
/config/flags; the switch is the server's environment, not the adapter's):
  keyless      no key reaches the server: provider noop, EMBEDDING_PROVIDER=local
               (Xenova/all-MiniLM-L6-v2 on the machine), no LLM feature
  with Gemini  GEMINI_API_KEY (the embedder reads only this name; the provider
               also takes GOOGLE_API_KEY), GEMINI_MODEL=gemini-3-flash-preview,
               EMBEDDING_PROVIDER=gemini (gemini-embedding-001, the one Gemini
               embedder it ships), AGENTMEMORY_AUTO_COMPRESS=true,
               GRAPH_EXTRACTION_ENABLED=true, CONSOLIDATION_ENABLED=true (the three
               flags /config/flags lists as needing an LLM). The import then
               runs /graph/build and /consolidate-pipeline

    AGENTMEMORY_URL      http://127.0.0.1:3111 (the REST port)
    AGENTMEMORY_SECRET   Bearer for a deployment with auth (empty on loopback)
    AGENTMEMORY_SCRATCH  folder for the transcript files the server imports
                         (default: the system temp folder; the server must see it)

Doors (the text is the MCP tool's text, as the client receives it; the
adapter parses it only to fill semantic/episodic for the checks):
  recall        `memory_recall` called with the question and limit 10 (its
                default); format is left to its default (full). The text is the
                JSON of the hits, each with title, facts and narrative, so a
                memory's content arrives two or three times, and a timestamp
                that is the event's date for an imported item and the time of
                the save for a memory_save. No cut (ADEBENCH_AGENTMEMORY_CUT=N)
  smart_search  `memory_smart_search` with the question and limit 10 (its
                default). It answers in its compact mode: the title of each hit,
                i.e. the first 80 characters of a memory and the hook name
                ("prompt_submit") of an observation; the details need a second
                call (expandIds) this door does not make

What maps and what does not (SKIP is honest, not a zero):
  cards          none: no entity cards, corrections or aliases. An alias is
                 saved as a sentence, like any memory
  fact updates   `memory_save` supersedes by itself: a new memory whose words
                 overlap an older one by Jaccard > 0.7 retires it (isLatest=false,
                 out of both indexes). write_fact is that plain save, no id given;
                 forget_memory is /forget. settle: nothing to wait for, the save
                 indexes (BM25 and vector) before it returns
  time           every hit carries a timestamp. `memory_save` takes no date: it
                 stamps the save, and that time is not the fact's age: in the
                 parsed semantic lines only an imported memory (origin "import")
                 is given its date. The export/import path keeps createdAt, so
                 import_memory and the dated synthetic facts go through /import;
                 the undated ones through memory_save, stamped with the day of
                 the run. Episodes go through the transcript import, which keeps
                 each turn's time. There is no day filter: `memory_timeline`
                 anchors on a date and returns the neighbours, and the adapter
                 keeps the anchor's day
  episodes       sessions of observations. With no LLM (keyless) an observation
                 is compressed without a model: the user's prompt is kept, the
                 assistant's reply is dropped (an empty "stop" observation), so
                 an episode's result is not searchable
  write-back     no ingest_exchange, SKIP: the normal path after a turn is the
                 hooks, and the Stop hook only ends the session, it does not send
                 the assistant's answer (only a subagent's stop carries its last
                 message). A probe there could never store the degraded answer
  live state     memory_save and recall: no TTL, no key. A new value is a plain
                 memory_save, nothing forgotten first: whether the old value
                 is retired (its Jaccard supersession) is agentmemory's doing.
                 working_clear forgets what was written. Slots (AGENTMEMORY_SLOTS)
                 are off by default and not served by recall
  files          `memory_file_history` takes paths, not a query: SKIP
  graph          knowledge-graph extraction needs an LLM (GRAPH_EXTRACTION_ENABLED
                 plus a key): off in keyless mode, SKIP. With Gemini the nodes are
                 extracted from observations (episodes), not from memories, so no
                 node is an entity card: edges per card SKIP; a node whose source
                 observations are all gone is an orphan (graph_orphans), a count
                 the harness reports without scoring when there are no cards
  abstention     recall has no relevance floor: it returns its nearest hits for
                 anything. Only an empty result is passed on as unknown terms
  declared bytes /agentmemory/mcp/tools, the list the MCP shim serves (54 tools)
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

from adebench.ade import competing_payload
from adebench.config import CFG, LOCAL_TZ, local_day

URL = os.environ.get("AGENTMEMORY_URL", "http://127.0.0.1:3111").rstrip("/")
SECRET = os.environ.get("AGENTMEMORY_SECRET", "")
SCRATCH = os.environ.get("AGENTMEMORY_SCRATCH", "")
DOORS = ("recall", "smart_search")
TOOL = {"recall": "memory_recall", "smart_search": "memory_smart_search"}
_STOP = {"what", "which", "who", "when", "where", "does", "is", "the", "a", "an", "how", "many", "much",
         "about", "with", "for", "and", "that", "this", "are", "was", "were", "have", "has", "do", "did"}
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


class AgentmemoryError(RuntimeError):
    pass


def _iso(when: str) -> str:
    """ISO datetime with a zone. A date alone is noon of that day; a datetime
    without a zone ('2026-09-10T09:12:00' or '2026-09-10 09:12:00') is local
    time (config.LOCAL_TZ), the benchmark's day, not UTC."""
    w = str(when).strip()
    if w.endswith("Z"):
        w = w[:-1] + "+00:00"
    dt = datetime.fromisoformat(w if (" " in w or "T" in w) else f"{w}T12:00:00")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_answer(text: str, query: str, door: str, origins: dict[str, str],
                 live_ids: set[str] | None = None) -> dict:
    """The raw answer from the MCP text of memory_recall / memory_smart_search.
    `summary` is that text as received; `semantic` (memories, ids mem_...) and
    `episodic` (observations) are parsed from it for the checks. A memory gets
    a date in its semantic line only when it was imported (origin "import"):
    then its timestamp is the event's date; after a memory_save it is the time
    of the save, which is not the fact's age."""
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        d = None
    if not isinstance(d, dict) or not isinstance(d.get("results"), list):
        raise AgentmemoryError(f"{door}: unexpected answer: {text[:200]}")
    live_ids = live_ids or set()
    semantic, episodic, working = [], [], []
    for h in d["results"]:
        if not isinstance(h, dict):
            continue
        o = h.get("observation") if isinstance(h.get("observation"), dict) else h
        oid = str(o.get("id") or h.get("obsId") or "")
        ts = str(o.get("timestamp") or h.get("timestamp") or "")
        if door == "smart_search":
            body = str(o.get("title") or "").strip()
        else:
            body = str(o.get("narrative") or "").strip() or " ".join(map(str, o.get("facts") or [])).strip()
        if oid.startswith("mem_"):
            dated = origins.get(oid) == "import" and _DAY.match(ts)
            semantic.append({"source": f"agentmemory:memory:{o.get('type') or ''}", "key": oid,
                             "content": f"[since {ts[:10]}] {body}" if dated else body,
                             "_score": h.get("score")})
            if oid in live_ids and ": " in body:
                k, _, v = body.partition(": ")
                working.append({"key": k, "value": v})
        else:
            episodic.append({"created_at": ts, "input_summary": body, "output_summary": "",
                             "key": oid, "session": h.get("sessionId") or o.get("sessionId")})
    unknown = []
    if not d["results"]:
        # nothing returned at all: the only abstention recall has
        unknown = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", query) if w.lower() not in _STOP][:3]
    return {"summary": text, "semantic": semantic, "cards": [], "episodic": episodic,
            "working": working, "unknown_terms": unknown, "_raw": d}


class AgentmemoryAdapter:
    def __init__(self) -> None:
        self.url = URL
        self.cut = int(os.environ.get("ADEBENCH_AGENTMEMORY_CUT", "0"))
        self.limit = int(os.environ.get("ADEBENCH_AGENTMEMORY_LIMIT", "10"))
        self._traces: list[dict] = []
        self._live: dict[tuple[str, str], list[str]] = {}   # (session, key) -> memory ids

    # ── HTTP ──────────────────────────────────────────────────────────────
    def _http(self, method: str, path: str, body: dict | None = None, door: str | None = None,
              timeout: float = 120, allow: tuple = ()) -> dict:
        headers = {"Content-Type": "application/json"}
        if SECRET:
            headers["Authorization"] = f"Bearer {SECRET}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method, headers=headers)
        t0 = time.perf_counter()
        code, raw = 0, b""
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                code, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            code, raw = e.code, e.read()
        except Exception as e:  # noqa: BLE001
            self._traces.append({"door": door or path.split("?")[0], "ms": (time.perf_counter() - t0) * 1000,
                                 "chars": 0, "http": 0})
            raise AgentmemoryError(f"{method} {path}: {type(e).__name__}: {e}") from e
        self._traces.append({"door": door or path.split("?")[0], "ms": (time.perf_counter() - t0) * 1000,
                             "chars": len(raw.decode("utf-8", "replace")), "http": code})
        text = raw.decode("utf-8", "replace")
        if code >= 400 and code not in allow:
            raise AgentmemoryError(f"{method} {path}: HTTP {code}: {text[:200]}")
        try:
            out = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError as e:
            raise AgentmemoryError(f"{method} {path}: not JSON: {text[:200]}") from e
        out = out if isinstance(out, dict) else {"_list": out}
        out.setdefault("_http", code)
        return out

    def _mcp(self, tool: str, args: dict) -> str:
        """The text an MCP client receives from `tool` (the shim forwards to this route)."""
        out = self._http("POST", "/agentmemory/mcp/call", {"name": tool, "arguments": args}, door=tool)
        content = out.get("content")
        if not isinstance(content, list):
            raise AgentmemoryError(f"{tool}: no content in {str(out)[:200]}")
        return "".join(str(c.get("text", "")) for c in content if isinstance(c, dict))

    # ── writing ───────────────────────────────────────────────────────────
    def save(self, text: str) -> str | None:
        """memory_save's route: the memory is stamped with the time of the save."""
        out = self._http("POST", "/agentmemory/remember", {"content": text})
        m = out.get("memory") if isinstance(out.get("memory"), dict) else {}
        if out.get("success") is False:
            raise AgentmemoryError(f"remember: {out.get('error')}")
        return m.get("id")

    def import_memories(self, items: list[tuple[str, str]]) -> list[str]:
        """The export/import path, strategy merge: [(text, written_at)] -> ids.
        A record is what memory_save would write (title = first 80 characters,
        type fact), with createdAt the original date."""
        mems, ids = [], []
        for text, when in items:
            ts = _iso(when)
            mid = f"mem_adebench_{uuid.uuid4().hex[:12]}"
            ids.append(mid)
            mems.append({"id": mid, "createdAt": ts, "updatedAt": ts, "type": "fact", "title": text[:80],
                         "content": text, "concepts": [], "files": [], "sessionIds": [], "strength": 7,
                         "version": 1, "supersedes": [], "isLatest": True})
        export = {"version": self.version(), "exportedAt": _now(), "sessions": [], "observations": {},
                  "summaries": [], "memories": mems}
        out = self._http("POST", "/agentmemory/import", {"exportData": export, "strategy": "merge"})
        if not out.get("success") or out.get("memories") != len(mems):
            raise AgentmemoryError(f"import: {str(out)[:200]}")
        return ids

    def import_transcript(self, session_id: str, turns: list[tuple[str, str, str]]) -> dict:
        """The transcript import (Claude Code JSONL): [(role, text, when)], one
        session. The server reads the file, so it is written where it can see it."""
        folder = SCRATCH or tempfile.gettempdir()
        path = os.path.join(folder, f"adebench-agentmemory-{session_id}.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            for role, text, when in turns:
                content = text if role == "user" else [{"type": "text", "text": text}]
                f.write(json.dumps({"type": role, "sessionId": session_id, "timestamp": _iso(when),
                                    "message": {"role": role, "content": content}}) + "\n")
        try:
            out = self._http("POST", "/agentmemory/replay/import-jsonl", {"path": path}, timeout=300)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        if not out.get("success") or not out.get("imported"):
            raise AgentmemoryError(f"import-jsonl: {str(out)[:200]}")
        return out

    def version(self) -> str:
        """The server's version, which the import requires in the export
        (read from /health, which carries it also when it answers 503)."""
        if not getattr(self, "_version", None):
            self._version = str(self._http("GET", "/agentmemory/health", allow=(503,)).get("version") or "")
        if not self._version:
            raise AgentmemoryError("/health carries no version: the import needs it")
        return self._version

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        """/health answers 503 with status "critical" when its own monitor
        sees CPU above 90% over the last 30 s (the local embedder does that
        under load): that is the service saying it is not healthy."""
        try:
            out = self._http("GET", "/agentmemory/health", timeout=30)
        except AgentmemoryError:
            return False
        return out.get("status") == "healthy"

    def warm_up(self) -> float | None:
        t0 = time.perf_counter()
        try:
            self._mcp("memory_recall", {"query": "hello", "limit": 1})
        except AgentmemoryError:
            return None
        return (time.perf_counter() - t0) * 1000

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return list(DOORS)

    def door_cut(self, door: str) -> int | None:
        return self.cut or None

    def _origins(self, ids: set[str]) -> dict[str, str]:
        """memory id -> origin channel ("import", "agent", ...). A recall hit
        does not say where a memory came from; /memories does. Cached, and
        read again when a hit names a memory not seen yet."""
        cache = getattr(self, "_origin_cache", None)
        if cache is None or not ids <= cache.keys():
            cache = {str(m.get("id")): str((m.get("origin") or {}).get("channel") or "")
                     for m in self._memories()}
            self._origin_cache = cache
        return cache

    def _answer(self, query: str, door: str = "recall") -> dict:
        tool = TOOL.get(door, "memory_recall")
        text = self._mcp(tool, {"query": query, "limit": self.limit})
        ids = set(re.findall(r'"(?:id|obsId)":\s*"(mem_[^"]+)"', text))
        live_ids = {m for v in self._live.values() for m in v}
        return parse_answer(text, query, door, self._origins(ids) if ids else {}, live_ids)

    def door_text(self, query: str, door: str) -> tuple[str, dict]:
        r = self._answer(query, door if door in DOORS else "recall")
        text = competing_payload(CFG.pressure) + r["summary"]
        return (text[:self.cut] if self.cut else text), r

    def ask(self, query: str) -> dict:
        return self._answer(query, "recall")

    # ── cards, corrections, aliases: none ─────────────────────────────────
    def cards(self) -> list[dict]:
        return []

    def corrections(self) -> list[dict]:
        return []

    def aliases(self) -> list[dict]:
        return []

    # ── facts and their lifecycle ─────────────────────────────────────────
    def _memories(self) -> list[dict]:
        out = self._http("GET", "/agentmemory/memories")
        mems = out.get("memories")
        if not isinstance(mems, list):
            raise AgentmemoryError(f"/memories: {str(out)[:200]}")
        return [m for m in mems if isinstance(m, dict)]

    def update_trace(self) -> dict:
        mems = self._memories()
        return {"memories": len(mems),
                "superseded_live": sum(1 for m in mems if m.get("isLatest") is False),
                "relation_updates": sum(1 for m in mems if m.get("supersedes"))}

    def event_date_share(self) -> tuple[int, int]:
        """A memory carries the event's date only when it came through the
        import with its createdAt; memory_save stamps the time of the save."""
        mems = [m for m in self._memories() if m.get("isLatest") is not False]
        dated = sum(1 for m in mems if (m.get("origin") or {}).get("channel") == "import")
        return (dated, len(mems))

    # ── episodes and time ─────────────────────────────────────────────────
    def _observations(self) -> list[dict]:
        out = self._http("GET", "/agentmemory/export", timeout=300)
        obs = out.get("observations")
        if not isinstance(obs, dict):
            raise AgentmemoryError(f"/export: {str(out)[:200]}")
        return [o for rows in obs.values() if isinstance(rows, list) for o in rows if isinstance(o, dict)]

    def recent_days(self, n: int) -> list[str]:
        days = {local_day(str(o.get("timestamp") or "")) for o in self._observations() if o.get("timestamp")}
        return sorted((d for d in days if _DAY.fullmatch(d)), reverse=True)[:n]

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        out = self._http("POST", "/agentmemory/timeline",
                         {"anchor": f"{day}T12:00:00Z", "before": limit, "after": limit})
        entries = out.get("entries")
        if not isinstance(entries, list):
            raise AgentmemoryError(f"/timeline: {str(out)[:200]}")
        eps = []
        for e in entries:
            o = e.get("observation") or {}
            ts = str(o.get("timestamp") or "")
            if local_day(ts) == day:   # the timeline is a window around the anchor, not a day filter
                eps.append({"created_at": ts, "input_summary": str(o.get("narrative") or ""),
                            "output_summary": "", "type": o.get("type")})
        return eps[:limit]

    def signed_episodes(self, prefix: str) -> int:
        return sum(1 for o in self._observations() if str(o.get("narrative") or "").startswith(prefix))

    # ── live state: memory_save / recall / forget ─────────────────────────
    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool:
        """A plain memory_save of "key: value". The previous value is NOT
        forgotten first: whether it is retired is agentmemory's supersession."""
        mid = self.save(f"{key}: {value}")
        if mid:
            self._live.setdefault((session, key), []).append(mid)
        return bool(mid)

    def working_read(self, session: str, key: str):
        for mid in reversed(self._live.get((session, key)) or []):   # the latest write first
            try:
                out = self._http("GET", f"/agentmemory/memories/{mid}")
            except AgentmemoryError as e:
                if "HTTP 404" in str(e):
                    continue
                raise
            m = out.get("memory") if isinstance(out.get("memory"), dict) else out
            text = str(m.get("content") or "")
            if text:
                return text.split(": ", 1)[1] if ": " in text else text
        return None

    def working_clear(self, session: str) -> None:
        for (s, _k), ids in list(self._live.items()):
            if s == session:
                for mid in ids:
                    self._forget_memory(mid)
        self._live = {k: v for k, v in self._live.items() if k[0] != session}

    def working_age_minutes(self, session: str, key: str) -> float | None:
        return None

    # ── files and graph ───────────────────────────────────────────────────
    def file_search(self, query: str, limit: int) -> list[str]:
        return []

    def graph_edges(self, entity: str) -> int:
        return 0

    def graph_orphans(self) -> tuple[int, int]:
        """(nodes whose source observations are all gone, nodes with sources).
        A graph node carries the ids of the observations it was extracted
        from; keyless there is no extraction and no node: (0, 0), SKIP."""
        nodes, offset = [], 0
        while True:
            out = self._http("POST", "/agentmemory/graph/query", {"limit": 500, "offset": offset})
            page = out.get("nodes")
            if not isinstance(page, list):
                raise AgentmemoryError(f"/graph/query: {str(out)[:200]}")
            nodes += [n for n in page if isinstance(n, dict)]
            offset += len(page)
            if not page or not out.get("truncated"):
                break
        sourced = [n for n in nodes if n.get("sourceObservationIds")]
        if not sourced:
            return (0, 0)
        alive = {str(o.get("id")) for o in self._observations()}
        orphans = sum(1 for n in sourced if not any(str(i) in alive for i in n["sourceObservationIds"]))
        return (orphans, len(sourced))

    def graph_counts(self) -> dict:
        out = self._http("GET", "/agentmemory/graph/stats")
        return {"nodes": out.get("totalNodes", 0), "edges": out.get("totalEdges", 0)}

    # ── report-only ───────────────────────────────────────────────────────
    def health_report(self) -> tuple[dict, list[str]]:
        measures, warnings = {}, []
        try:
            h = self._http("GET", "/agentmemory/health", timeout=30, allow=(503,))
            measures["status"] = h.get("status")
            measures["http"] = h.get("_http")
            measures["version"] = h.get("version")
            measures["alerts"] = (h.get("health") or {}).get("alerts")
            measures["notes"] = (h.get("health") or {}).get("notes")
            if h.get("_http") != 200:
                warnings.append(f"/health answered HTTP {h.get('_http')} status {h.get('status')}: "
                                f"{measures['alerts']} (its monitor averages CPU over 30 s)")
        except AgentmemoryError as e:
            warnings.append(str(e)[:160])
        try:
            f = self._http("GET", "/agentmemory/config/flags", timeout=30)
            measures["llm_provider"] = f.get("provider")
            measures["embedding_provider"] = f.get("embeddingProvider")
            measures["flags_enabled"] = [x.get("key") for x in f.get("flags") or [] if x.get("enabled")]
        except AgentmemoryError as e:
            warnings.append(str(e)[:160])
        try:
            mems = self._memories()
            measures["memories"] = len(mems)
            measures["memories_latest"] = sum(1 for m in mems if m.get("isLatest") is not False)
        except AgentmemoryError as e:
            warnings.append(str(e)[:160])
        if measures.get("llm_provider") in (None, "noop"):
            warnings.append("no entity cards, file search or graph (extraction needs an LLM): those sections are SKIP")
            warnings.append("keyless mode: an assistant reply is dropped by the model-free compression, "
                            "so episodes keep only the user's prompt")
        else:
            try:
                measures["graph"] = self.graph_counts()
            except AgentmemoryError as e:
                warnings.append(str(e)[:160])
            warnings.append("no entity cards and no file search: those sections are SKIP; the graph is "
                            "extracted from episodes only: no entity card to check edges on, the orphan count "
                            "is reported, not scored")
            warnings.append("the transcript import compresses without a model whatever the provider: "
                            "the assistant's reply is dropped, episodes keep only the user's prompt")
        return measures, warnings

    def measured_doors(self) -> list[str]:
        return ["memory_recall", "memory_smart_search"]

    def traces(self) -> list[dict]:
        return list(self._traces)

    def probe_doors(self, questions: list[str]) -> None:
        for q in questions:
            try:
                self._answer(q, "smart_search")
            except AgentmemoryError:
                pass

    # ── optional ──────────────────────────────────────────────────────────
    def stored_mentions(self, phrase: str) -> int:
        low = phrase.lower()
        n = sum(1 for m in self._memories() if low in str(m.get("content") or "").lower())
        n += sum(1 for o in self._observations()
                 if low in (str(o.get("narrative") or "") + " " + " ".join(map(str, o.get("facts") or []))).lower())
        return n

    def _forget_memory(self, memory_id: str) -> bool:
        out = self._http("POST", "/agentmemory/forget", {"memoryId": memory_id})
        return memory_id in (out.get("deletedMemoryIds") or []) or (out.get("deleted") or 0) > 0

    def write_fact(self, text: str):
        return self.save(text)

    def settle(self) -> None:
        """Nothing pending: /remember adds the memory to the BM25 and vector
        indexes before it returns."""
        return None

    def forget_memory(self, memory_id: str) -> bool:
        return self._forget_memory(memory_id)

    def import_memory(self, text: str, written_at: str):
        return self.import_memories([(text, written_at)])[0]

    def declared_bytes(self) -> int | None:
        out = self._http("GET", "/agentmemory/mcp/tools")
        tools = out.get("tools")
        if not isinstance(tools, list):
            return None
        return len(json.dumps(tools, separators=(",", ":")).encode("utf-8"))
