"""Adapter for Hindsight (github.com/vectorize-io/hindsight): agent memory with
world facts, experiences and observations, reached over its per-bank MCP
endpoint.

Everything goes through the MCP tools of one bank, the door an agent has:
`sync_retain` to write (an LLM extracts facts, entities and relations, with
the event's own time), `recall` to read (the fused, reranked results),
`delete_document` to remove what a write produced, `list_memories` and
`get_memory` for the report. `reflect` is left out: it answers, and the
benchmark measures what reaches the model, not answers. No Hindsight code is
imported.

    docker run -d -p 127.0.0.1:8888:8888 -e HINDSIGHT_API_LLM_PROVIDER=gemini \\
        -e HINDSIGHT_API_LLM_API_KEY=... -e HINDSIGHT_API_LLM_MODEL=gemini-3.5-flash-lite \\
        -v hindsight-data:/home/hindsight/.pg0 ghcr.io/vectorize-io/hindsight:latest
    python examples/hindsight_import.py
    python -m adebench --adapter adebench.hindsight:HindsightAdapter --cases sets/quick/cases

    HINDSIGHT_URL      http://127.0.0.1:8888
    HINDSIGHT_BANK     adebench           the bank measured (a scratch one)
    HINDSIGHT_TOKEN    Bearer for a deployment with the API-key tenant extension
    ADEBENCH_HINDSIGHT_BUDGET   low | mid | high   recall thoroughness (default mid)
    ADEBENCH_HINDSIGHT_MAX_TOKENS  the recall's own token cap (default 2000)
    ADEBENCH_HINDSIGHT_MIN_SCORE   final score under which a result is not delivered (default 0: all)

Doors:
  recall  what `recall` returns for the question, in its order, each result
          with the time it was mentioned; no cut (ADEBENCH_HINDSIGHT_CUT=N)

What maps and what does not (SKIP is honest, not a zero):
  cards          none as such: observations and mental models are syntheses,
                 not entity cards. Corrections, aliases: none
  fact updates   no supersede trace is exposed; the harness probe runs through
                 write_fact (sync_retain) and forget_memory (delete_document)
  time           memories carry `mentioned_at` (and `occurred_*` when the
                 extractor finds a date); the day filter is done on
                 list_memories in the adapter
  live state     NOT RUN: retain runs an extractor, and an arbitrary string ("the
                 password of the day is sunflower") is not a fact it keeps. Run
                 without the live_state section
  files, graph   not exposed as such: SKIP
  declared bytes tools/list of the bank endpoint, 72 KB for 36 tools

Every write costs an LLM call on Hindsight's side: the extraction model is
part of the configuration and the report says which one ran.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
import uuid

from adebench.ade import competing_payload
from adebench.config import CFG

BASE = os.environ.get("HINDSIGHT_URL", "http://127.0.0.1:8888").rstrip("/")
BANK = os.environ.get("HINDSIGHT_BANK", "adebench")
TOKEN = os.environ.get("HINDSIGHT_TOKEN", "")
DOORS = ("recall",)
_STOP = {"what", "which", "who", "when", "where", "does", "is", "the", "how", "many", "much", "about",
         "with", "for", "and", "that", "this", "are", "was", "were", "have", "has", "did", "module", "service"}


class HindsightError(RuntimeError):
    pass


class _Mcp:
    """One MCP session on a background loop, driven synchronously."""

    def __init__(self, url: str, headers: dict) -> None:
        self.url, self.headers = url, headers
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.session = None
        self._stack = None
        self.tools: list = []
        self._run(self._open())

    def _run(self, coro, timeout: float = 600):
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
        data = getattr(res, "structuredContent", None)
        if data is None and text.strip().startswith(("{", "[")):
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = None
        return {"text": text, "data": data, "error": bool(getattr(res, "isError", False))}

    def call(self, name: str, args: dict, timeout: float = 600) -> dict:
        return self._run(self._call(name, args), timeout)


class HindsightAdapter:
    def __init__(self) -> None:
        self.base = BASE
        self.bank = BANK
        self.url = f"{self.base}/mcp/{self.bank}/"
        self.budget = os.environ.get("ADEBENCH_HINDSIGHT_BUDGET", "mid")
        self.max_tokens = int(os.environ.get("ADEBENCH_HINDSIGHT_MAX_TOKENS", "2000"))
        self.cut = int(os.environ.get("ADEBENCH_HINDSIGHT_CUT", "0"))
        # 0 = the deployment default: every result recall returns is delivered.
        # A floor (0.1 separates the reranker's matches, 1.0 and more, from the
        # rest, 1e-5 to 1e-2) trades the door for abstention: see the README.
        self.min_score = float(os.environ.get("ADEBENCH_HINDSIGHT_MIN_SCORE", "0"))
        self._traces: list[dict] = []
        self._mcp: _Mcp | None = None
        self._live: dict[tuple[str, str], str] = {}   # (session, key) -> document id
        self._docs: dict[str, str] = {}                # write_fact id -> document id

    # ── the MCP door ──────────────────────────────────────────────────────
    def _conn(self) -> _Mcp:
        if self._mcp is None:
            headers = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}
            try:
                self._mcp = _Mcp(self.url, headers)
            except Exception as e:  # noqa: BLE001
                raise HindsightError(f"cannot reach {self.url}: {type(e).__name__}: {e}") from e
        return self._mcp

    def _tool(self, name: str, args: dict, timeout: float = 600) -> dict:
        t0 = time.perf_counter()
        try:
            out = self._conn().call(name, args, timeout)
        except HindsightError:
            raise
        except Exception as e:  # noqa: BLE001
            self._traces.append({"door": name, "ms": (time.perf_counter() - t0) * 1000, "chars": 0, "http": 500})
            raise HindsightError(f"{name}: {type(e).__name__}: {e}") from e
        d = out.get("data") if isinstance(out.get("data"), dict) else {}
        failed = out.get("error") or str(d.get("status", "")).lower() == "error"
        self._traces.append({"door": name, "ms": (time.perf_counter() - t0) * 1000,
                             "chars": len(out.get("text", "")), "http": 500 if failed else 200})
        if failed:
            raise HindsightError(f"{name}: {(d.get('message') or out.get('text', ''))[:200]}")
        return out

    @staticmethod
    def _payload(out: dict) -> dict:
        d = out.get("data")
        return d if isinstance(d, dict) else {}

    # ── writing ───────────────────────────────────────────────────────────
    def retain(self, text: str, when: str | None = None, document_id: str | None = None,
               context: str | None = None) -> tuple[str, list[str]]:
        """One sync_retain: returns (document id, memory ids). The document id
        is the handle for removal: delete_document takes the memories with it."""
        doc = document_id or f"adebench-{uuid.uuid4().hex[:12]}"
        args = {"content": text, "document_id": doc}
        if when:
            ts = when if "T" in when else f"{when}T12:00:00"
            if not re.search(r"(Z|[+-]\d\d:\d\d)$", ts):
                ts += "Z"
            args["timestamp"] = ts
        if context:
            args["context"] = context
        d = self._payload(self._tool("sync_retain", args))
        return doc, [str(m) for m in (d.get("memory_ids") or [])]

    def delete_document(self, document_id: str) -> bool:
        """True when the document is gone: with its memories, or with none to
        remove because the extractor kept nothing of it."""
        try:
            d = self._payload(self._tool("delete_document", {"document_id": document_id}))
        except HindsightError:
            return False
        return str(d.get("status")) == "deleted"

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        import urllib.request
        try:
            with urllib.request.urlopen(f"{self.base}/health", timeout=15) as r:
                return "healthy" in r.read().decode("utf-8", "replace")
        except OSError:
            return False

    def warm_up(self) -> float | None:
        t0 = time.perf_counter()
        try:
            self._recall("hello", budget="low")
        except HindsightError:
            return None
        return (time.perf_counter() - t0) * 1000

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return list(DOORS)

    def door_cut(self, door: str) -> int | None:
        return self.cut or None

    def _recall(self, query: str, budget: str | None = None) -> dict:
        return self._payload(self._tool("recall", {"query": query, "budget": budget or self.budget,
                                                   "max_tokens": self.max_tokens}))

    def _answer(self, query: str) -> dict:
        d = self._recall(query)
        semantic, working = [], []
        live_docs = {doc: key for (_, key), doc in self._live.items()}
        for h in d.get("results") or []:
            if not isinstance(h, dict):
                continue
            text = str(h.get("text") or "").strip()
            if not text:
                continue
            # recall scores each result: 1.0 and more when the reranker agrees,
            # 1e-5 to 1e-2 when it does not, and on a question with no match it
            # returns the whole bank at 1e-5. With ADEBENCH_HINDSIGHT_MIN_SCORE
            # a result under the floor is not delivered; the default delivers
            # everything, as the deployment does (min_scores off).
            if self.min_score and float((h.get("scores") or {}).get("final") or 0) < self.min_score:
                continue
            when = str(h.get("occurred_start") or h.get("mentioned_at") or "")[:10]
            kind = str(h.get("fact_type") or "memory")
            semantic.append({"source": f"hindsight:{kind}", "key": h.get("id"),
                             "content": f"[since {when}] {text}" if re.match(r"\d{4}-\d{2}-\d{2}", when) else text,
                             "_score": (h.get("scores") or {}).get("final")})
            doc = str(h.get("document_id") or "")
            if doc in live_docs and ": " in text:
                key, _, value = text.partition(": ")
                working.append({"key": live_docs[doc], "value": value})
        summary = "\n".join(s["content"] for s in semantic)
        unknown = []
        if not semantic:
            # nothing delivered: the door says so instead of staying silent (an
            # empty answer reads as an adapter error, not as a miss)
            summary = "recall: no result" + (f" above the score floor {self.min_score}" if self.min_score else "")
            # recall returned nothing it would serve: Hindsight's own abstention
            unknown = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", query) if w.lower() not in _STOP][:3]
        return {"summary": summary, "semantic": semantic, "cards": [], "episodic": [],
                "working": working, "unknown_terms": unknown, "_raw": d}

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
    def _memories(self, q: str | None = None, limit: int = 200, kind: str | None = None) -> list[dict]:
        out: list[dict] = []
        offset = 0
        while True:
            args = {"limit": limit, "offset": offset}
            if q:
                args["q"] = q
            if kind:
                args["type"] = kind
            d = self._payload(self._tool("list_memories", args))
            items = [i for i in (d.get("items") or []) if isinstance(i, dict)]
            out.extend(items)
            if len(items) < limit or len(out) >= int(d.get("total") or 0):
                break
            offset += limit
        return out

    def update_trace(self) -> dict:
        by_type: dict[str, int] = {}
        for m in self._memories():
            t = str(m.get("fact_type") or "?")
            by_type[t] = by_type.get(t, 0) + 1
        return {"memories_by_type": by_type, "superseded_live": 0, "relation_updates": 0}

    def event_date_share(self) -> tuple[int, int]:
        ms = self._memories()
        dated = sum(1 for m in ms if m.get("occurred_start") or m.get("mentioned_at"))
        return (dated, len(ms))

    # ── episodes and time ─────────────────────────────────────────────────
    @staticmethod
    def _day(m: dict) -> str:
        return str(m.get("occurred_start") or m.get("mentioned_at") or m.get("date") or "")[:10]

    def recent_days(self, n: int) -> list[str]:
        days = {self._day(m) for m in self._memories(kind="experience")} or {self._day(m) for m in self._memories()}
        return sorted((d for d in days if d), reverse=True)[:n]

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        out = []
        for m in self._memories():
            if self._day(m) == day:
                out.append({"created_at": str(m.get("occurred_start") or m.get("mentioned_at") or ""),
                            "input_summary": str(m.get("text") or ""), "output_summary": ""})
        return out[:limit]

    def signed_episodes(self, prefix: str) -> int:
        return sum(1 for m in self._memories(q=prefix) if str(m.get("text") or "").startswith(prefix))

    # ── live state: retain / recall / delete_document ─────────────────────
    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool:
        old = self._live.pop((session, key), None)
        if old:
            self.delete_document(old)
        doc, ids = self.retain(f"{key}: {value}", document_id=f"adebench-live-{uuid.uuid4().hex[:10]}",
                               context="live state")
        if not ids:
            return False
        self._live[(session, key)] = doc
        return True

    def working_read(self, session: str, key: str):
        doc = self._live.get((session, key))
        if not doc:
            return None
        for m in self._memories(q=key):
            if str(m.get("document_id")) == doc:
                text = str(m.get("text") or "")
                return text.split(":", 1)[1].strip() if ":" in text else text
        return None

    def working_clear(self, session: str) -> None:
        for (s, k), doc in list(self._live.items()):
            if s == session:
                self.delete_document(doc)
                self._live.pop((s, k), None)

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
            measures["bank"] = self._payload(self._tool("get_bank", {}, timeout=60))
        except HindsightError as e:
            warnings.append(str(e)[:120])
        measures["memories_by_type"] = self.update_trace()["memories_by_type"]
        warnings.append("cards, files and graph edges are not exposed by the bank's MCP surface: those sections are SKIP")
        return measures, warnings

    def measured_doors(self) -> list[str]:
        return ["recall"]

    def traces(self) -> list[dict]:
        return list(self._traces)

    def probe_doors(self, questions: list[str]) -> None:
        return None

    # ── optional ──────────────────────────────────────────────────────────
    def stored_mentions(self, phrase: str) -> int:
        low = phrase.lower()
        return sum(1 for m in self._memories(q=phrase) if low in str(m.get("text") or "").lower())

    def write_fact(self, text: str):
        doc, ids = self.retain(text)
        if not ids:
            return None
        self._docs[doc] = doc
        return doc

    def forget_memory(self, memory_id: str) -> bool:
        self._docs.pop(memory_id, None)
        return self.delete_document(memory_id)

    def import_memory(self, text: str, written_at: str):
        doc, _ids = self.retain(text, when=written_at)
        return doc

    def ingest_exchange(self, question: str, answer: str):
        # the extractor decides what of the exchange becomes a memory; an
        # exchange it keeps nothing of is the case the write-back probe wants
        doc, _ids = self.retain(f"User: {question}\nAssistant: {answer}", context="conversation")
        return doc

    def declared_bytes(self) -> int | None:
        try:
            tools = self._conn().tools
        except HindsightError:
            return None
        return len(json.dumps([t.model_dump() for t in tools], separators=(",", ":")).encode("utf-8"))
