"""Adapter for supermemory (github.com/supermemoryai/supermemory): a memory and
context engine, run self-hosted as the one-binary "supermemory local" server,
reached over its REST API.

Everything goes through the HTTP API a client has: `POST /v3/documents` to
write (a document is chunked, embedded, and a memory agent, an LLM with
tools, extracts memory entries from it, deciding by itself whether a new
entry updates an existing one), `POST /v3/documents/batch` with
`documentDate` for dated history, `POST /v4/search` to read, `POST
/v4/profile` for the profile door, `POST /v4/memories` for a memory written
directly (no extraction), `DELETE /v4/memories` to forget, `DELETE
/v3/documents/{id}` to remove a document and what was extracted from it,
`/v4/memories/list` and `/v3/documents/list` for the report. No supermemory
code is imported; urllib only.

    supermemory-server (0.0.8, windows-x64 release binary), with
        SUPERMEMORY_DATA_DIR=<scratch dir> PORT=3951 GEMINI_API_KEY=<key>
        (the native Gemini provider, whose model is fixed in the binary:
        gemini-3.1-flash-lite-preview; embeddings: local bge-base-en-v1.5,
        the self-hosted default). This is the reference setup. A local model
        through OPENAI_BASE_URL=http://localhost:11434/v1 also runs (gpt-oss:20b
        did, at ~2 min per document; llama3.1:8b extracted nothing), but it is
        not how the server is meant to run and is not the reference.
    python examples/supermemory_import.py
    ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.supermemory:SupermemoryAdapter \\
        --cases examples/synthetic_data/cases --history /tmp/supermemory-run --no-sandbox-test --write-back

    SUPERMEMORY_URL        http://localhost:3951
    SUPERMEMORY_CONTAINER  adebench          the container tag measured (a scratch one)
    SUPERMEMORY_TOKEN      Bearer for the server (empty: the local server applies its
                           own key to unauthenticated localhost requests)
    ADEBENCH_SUPERMEMORY_LIMIT      results per search (default 10, the API default)
    ADEBENCH_SUPERMEMORY_THRESHOLD  search threshold (default: not sent, the API's 0.6)
    ADEBENCH_SUPERMEMORY_SETTLE_S   longest wait for a write to be processed (default 900)
    ADEBENCH_SUPERMEMORY_CUT        character budget of the doors (default 0: no cut)
    SUPERMEMORY_SERVER_VERSION      what the report says ran (default 0.0.8)
    SUPERMEMORY_LLM                 (default gemini-3.1-flash-lite-preview, fixed by the
                                    binary for the Gemini provider)
    SUPERMEMORY_EMBEDDINGS          (default Xenova/bge-base-en-v1.5 local, 768d)

Doors:
  memories  what `/v4/search` returns (searchMode memories, the default): the
            latest version of each memory entry, in its order, each with its
            event date, else its source document's documentDate; no cut
  hybrid    `/v4/search` with searchMode hybrid: memory entries and document
            chunks
  profile   what `/v4/profile` returns with the question: the container's
            static and dynamic profile, then the search results

What maps and what does not (SKIP is honest, not a zero):
  cards          none: a profile is one per container, not per entity. Corrections,
                 aliases: none
  fact updates   VERSIONED: when the memory agent decides a new entry updates an
                 old one, the new one becomes version n+1 and the old one stays
                 stored as history (`isLatest` false); search serves the latest.
                 `PATCH /v4/memories` is the client-named update (by id) and is
                 NOT used: the harness probe writes plain documents (write_fact)
                 and lets the agent decide. Whether the old value comes back
                 through the door is exactly what the stale-value checks show
  forget         SOFT: `DELETE /v4/memories` marks an entry forgotten, it stays
                 stored (search can include it with include.forgottenMemories).
                 What the probes wrote is removed with `DELETE /v3/documents/{id}`,
                 which drops the document and the entries extracted from it. A
                 404 counts as removed only for an id this adapter already deleted;
                 an id it never saw is a failed removal
  update trace   /v4/memories/list returns only the latest, non-forgotten
                 entries: forgotten and superseded entries are not observable
                 there, and the report says None, not 0
  time           documents carry `documentDate` (kept at day precision), entries
                 carry the event dates the agent extracted; the day filter is done
                 on /v3/documents/list in the adapter (there is no day endpoint)
  live state     `POST /v4/memories`, the direct write ("immediately searchable",
                 no extraction). The write creates a backing document; an
                 overwrite or a clear deletes that document (hard), which drops
                 the entry too. Only when the API returns no document id does it
                 fall back to `DELETE /v4/memories` (soft forget); what is left
                 behind is counted in the report (live_state_writes.residue). No
                 TTL, no live-state key
  settle         waits until every document written is `done` (status and
                 dreamingStatus): extraction runs on the LLM, minutes per document
                 on a laptop; the waits are in the report (health_report).
                 import_memory (batch + documentDate) returns after that wait too.
                 Seen on 0.0.8 windows-x64: a 21-document batch stalled every
                 document in "maintain-container-description" for good (no LLM
                 call, no CPU); the import script sends one document per call
  files, graph   not exposed as such: SKIP (relations are served inside results,
                 no edge listing)
  declared bytes no MCP server in the self-hosted binary: not measured
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from datetime import datetime, timezone

from adebench.ade import competing_payload
from adebench.config import CFG, LOCAL_TZ

BASE = os.environ.get("SUPERMEMORY_URL", "http://localhost:3951").rstrip("/")
CONTAINER = os.environ.get("SUPERMEMORY_CONTAINER", "adebench")
TOKEN = os.environ.get("SUPERMEMORY_TOKEN", "")
DOORS = ("memories", "hybrid", "profile")
SETUP = {
    "server": "supermemory-server " + os.environ.get("SUPERMEMORY_SERVER_VERSION", "0.0.8"),
    "llm": os.environ.get("SUPERMEMORY_LLM",
                          "gemini-3.1-flash-lite-preview (native Gemini provider, fixed by the binary)"),
    "embeddings": os.environ.get("SUPERMEMORY_EMBEDDINGS",
                                 "Xenova/bge-base-en-v1.5, local, 768d (the self-hosted default)"),
}
_STOP = {"what", "which", "who", "when", "where", "does", "is", "the", "a", "an", "how", "many", "much",
         "about", "with", "for", "and", "that", "this", "are", "was", "were", "have", "has", "do", "did"}
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


class SupermemoryError(RuntimeError):
    pass


def _iso(when: str) -> str:
    """An ISO date or datetime as an RFC 3339 datetime. A naive time is the
    owner's local time (adebench's LOCAL_TZ) and is converted to UTC; a date
    alone is taken at local noon; a time with a zone is kept as it is."""
    ts = when if "T" in when else f"{when}T12:00:00"
    if re.search(r"(Z|[+-]\d\d:\d\d)$", ts):
        return ts
    dt = datetime.fromisoformat(ts).replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class SupermemoryAdapter:
    def __init__(self) -> None:
        self.base = BASE
        self.container = CONTAINER
        self.cut = int(os.environ.get("ADEBENCH_SUPERMEMORY_CUT", "0"))
        self.limit = int(os.environ.get("ADEBENCH_SUPERMEMORY_LIMIT", "10"))
        thr = os.environ.get("ADEBENCH_SUPERMEMORY_THRESHOLD", "")
        self.threshold = float(thr) if thr else None
        self.settle_max_s = float(os.environ.get("ADEBENCH_SUPERMEMORY_SETTLE_S", "900"))
        self._traces: list[dict] = []
        self._pending: list[str] = []                    # document ids not yet seen done
        self._settles: list[float] = []                  # seconds each settle() waited
        self._live: dict[tuple[str, str], str] = {}      # (session, key) -> memory id
        self._live_docs: dict[str, str | None] = {}     # live memory id -> backing document id
        self._deleted: set[str] = set()                  # document ids this adapter removed
        self._unsettled: list[list[str]] = []           # documents still pending after a settle
        self._live_stats = {"written": 0, "hard_deleted": 0, "soft_forgotten": 0, "failed": 0}

    # ── HTTP ──────────────────────────────────────────────────────────────
    def _req(self, method: str, path: str, body: dict | None = None, timeout: float = 120,
             ok_codes: tuple = (200, 201, 204)):
        headers = {"Content-Type": "application/json"}
        if TOKEN:
            headers["Authorization"] = f"Bearer {TOKEN}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        t0 = time.perf_counter()
        code, raw = 0, b""
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                code, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            code, raw = e.code, e.read()
        except Exception as e:  # noqa: BLE001
            self._traces.append({"door": f"{method} {path.split('?')[0]}", "ms": (time.perf_counter() - t0) * 1000,
                                 "chars": 0, "http": 0})
            raise SupermemoryError(f"{method} {path}: {type(e).__name__}: {e}") from e
        self._traces.append({"door": f"{method} {path.split('?')[0]}", "ms": (time.perf_counter() - t0) * 1000,
                             "chars": len(raw), "http": code})
        if code not in ok_codes:
            raise SupermemoryError(f"{method} {path}: HTTP {code}: {raw[:200].decode('utf-8', 'replace')}")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"_text": raw.decode("utf-8", "replace")}

    # ── writing ───────────────────────────────────────────────────────────
    def add_document(self, content: str, when: str | None = None, kind: str | None = None) -> str | None:
        """One document through the normal ingest path (extraction by the
        memory agent). `when` becomes its documentDate."""
        body: dict = {"content": content, "containerTag": self.container}
        if when:
            body["documentDate"] = _iso(when)
        if kind:
            body["metadata"] = {"kind": kind}
        d = self._req("POST", "/v3/documents", body)
        did = d.get("id") if isinstance(d, dict) else None
        if did:
            self._pending.append(did)
        return did

    def add_batch(self, docs: list[dict]) -> list[str]:
        """The historical backfill path: documents with documentDate, oldest first."""
        body = {"containerTag": self.container, "documents": docs}
        d = self._req("POST", "/v3/documents/batch", body, timeout=300)
        ids = []
        for r in (d.get("results") or d.get("documents") or []) if isinstance(d, dict) else []:
            if isinstance(r, dict) and r.get("id"):
                ids.append(r["id"])
        if isinstance(d, dict) and d.get("failed"):
            raise SupermemoryError(f"batch: {d.get('failed')} documents failed: {json.dumps(d)[:300]}")
        self._pending.extend(ids)
        return ids

    def document(self, doc_id: str) -> dict:
        return self._req("GET", f"/v3/documents/{doc_id}")

    def wait_done(self, ids: list[str], max_s: float | None = None) -> dict:
        """Poll documents until status and dreamingStatus are done (or failed)."""
        deadline = time.perf_counter() + (self.settle_max_s if max_s is None else max_s)
        left = list(dict.fromkeys(ids))
        states: dict[str, str] = {}
        while left:
            nxt = []
            for i in left:
                try:
                    d = self.document(i)
                except SupermemoryError as e:
                    if "HTTP 404" in str(e):
                        # gone after our own delete, or never there at all
                        states[i] = "deleted" if i in self._deleted else "missing"
                        continue
                    raise
                st, dr = d.get("status"), d.get("dreamingStatus")
                if st == "failed":
                    states[i] = "failed"
                elif st == "done" and dr in (None, "done", "failed", "skipped"):
                    states[i] = "done"
                else:
                    states[i] = f"{st}/{dr}"
                    nxt.append(i)
            left = nxt
            if not left or time.perf_counter() >= deadline:
                break
            time.sleep(2)
        return states

    def settle(self) -> None:
        if not self._pending:
            return
        t0 = time.perf_counter()
        states = self.wait_done(self._pending)
        self._settles.append(round(time.perf_counter() - t0, 1))
        self._pending = [i for i, s in states.items() if s not in ("done", "failed", "deleted", "missing")]
        if self._pending:
            # not processed within the wait: the door is asked anyway, and the
            # report says so (health_report)
            self._unsettled.append(list(self._pending))

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        """The server says ok AND a scoped search answers 200: a down server,
        or one that cannot search, is not healthy."""
        try:
            h = self._req("GET", "/v3/health", timeout=15)
            if not (isinstance(h, dict) and h.get("status") == "ok"):
                return False
            self._search("health check", limit=1)
        except SupermemoryError:
            return False
        return True

    def warm_up(self) -> float | None:
        t0 = time.perf_counter()
        try:
            self._search("hello", limit=1)
        except SupermemoryError:
            return None
        return (time.perf_counter() - t0) * 1000

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return list(DOORS)

    def door_cut(self, door: str) -> int | None:
        return self.cut or None

    def _search(self, query: str, mode: str = "memories", limit: int | None = None) -> dict:
        body: dict = {"q": query, "containerTag": self.container, "limit": limit or self.limit,
                      "include": {"documents": True}}
        if mode != "memories":
            body["searchMode"] = mode
        if self.threshold is not None:
            body["threshold"] = self.threshold
        return self._req("POST", "/v4/search", body)

    @staticmethod
    def _when(h: dict) -> str:
        """The date a result carries: its event date, else its source
        document's documentDate. Never the write time."""
        tc = (h.get("metadata") or {}).get("temporalContext") or {}
        ev = tc.get("eventDate")
        if isinstance(ev, list) and ev and _ISO.match(str(ev[0])):
            return str(ev[0])[:10]
        if tc.get("documentDate") and _ISO.match(str(tc["documentDate"])):
            return str(tc["documentDate"])[:10]
        for doc in h.get("documents") or []:
            dtc = ((doc or {}).get("metadata") or {}).get("temporalContext") or {}
            if dtc.get("documentDate") and _ISO.match(str(dtc["documentDate"])):
                return str(dtc["documentDate"])[:10]
        return ""

    @staticmethod
    def _is_episode(h: dict) -> bool:
        return any(((doc or {}).get("metadata") or {}).get("kind") == "episode" for doc in h.get("documents") or [])

    def _hits(self, d: dict) -> tuple[list[dict], list[dict]]:
        semantic, episodic = [], []
        for h in (d.get("results") or []) if isinstance(d, dict) else []:
            text = str(h.get("memory") or h.get("chunk") or "").strip()
            if not text:
                continue
            when = self._when(h)
            kind = "memory" if h.get("memory") else "chunk"
            line = f"[{when}] {text}" if when else text
            semantic.append({"source": f"supermemory:{kind}", "key": h.get("id"), "content": line,
                             "_score": h.get("similarity"), "_version": h.get("version")})
            if self._is_episode(h):
                episodic.append({"created_at": when, "input_summary": text, "output_summary": ""})
        return semantic, episodic

    def _answer(self, query: str, door: str = "memories") -> dict:
        profile_lines: list[str] = []
        if door == "profile":
            body: dict = {"containerTag": self.container, "q": query}
            if self.threshold is not None:
                body["threshold"] = self.threshold
            d = self._req("POST", "/v4/profile", body)
            p = d.get("profile") or {}
            profile_lines = [str(x) for x in (p.get("static") or []) + (p.get("dynamic") or [])]
            d = d.get("searchResults") or {}
        else:
            d = self._search(query, mode="hybrid" if door == "hybrid" else "memories")
        semantic, episodic = self._hits(d)
        live_ids = {mid: key for (_, key), mid in self._live.items()}
        working = []
        for s in semantic:
            if s["key"] in live_ids and ": " in s["content"]:
                working.append({"key": live_ids[s["key"]],
                                "value": s["content"].split("] ", 1)[-1].partition(": ")[2]})
        lines = profile_lines + [s["content"] for s in semantic]
        summary = "\n".join(lines)
        # no result at all: supermemory found nothing over its threshold. That
        # is its abstention, and the door passes it on as unknown terms.
        unknown = []
        if not semantic:
            unknown = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", query) if w.lower() not in _STOP][:3]
        return {"summary": summary, "semantic": semantic, "cards": [], "episodic": episodic,
                "working": working, "unknown_terms": unknown, "_raw": d}

    def door_text(self, query: str, door: str) -> tuple[str, dict]:
        r = self._answer(query, door if door in DOORS else "memories")
        text = competing_payload(CFG.pressure) + r["summary"]
        return (text[:self.cut] if self.cut else text), r

    def ask(self, query: str) -> dict:
        return self._answer(query, "memories")

    # ── cards, corrections, aliases: none ─────────────────────────────────
    def cards(self) -> list[dict]:
        return []

    def corrections(self) -> list[dict]:
        return []

    def aliases(self) -> list[dict]:
        return []

    # ── facts and their lifecycle ─────────────────────────────────────────
    def _memories(self) -> list[dict]:
        out: list[dict] = []
        for page in range(1, 50):
            d = self._req("POST", "/v4/memories/list",
                          {"containerTags": [self.container], "limit": 100, "page": page})
            items = d.get("memoryEntries") or []
            out.extend(items)
            pg = d.get("pagination") or {}
            if not items or page >= int(pg.get("totalPages") or 1):
                break
        return out

    def _documents(self, content: bool = False) -> list[dict]:
        out: list[dict] = []
        for page in range(1, 50):
            d = self._req("POST", "/v3/documents/list",
                          {"containerTags": [self.container], "limit": 100, "page": page,
                           "includeContent": content})
            items = d.get("memories") or d.get("documents") or []
            out.extend(items)
            pg = d.get("pagination") or {}
            if not items or page >= int(pg.get("totalPages") or 1):
                break
        return out

    def update_trace(self) -> dict:
        """/v4/memories/list returns the latest, non-forgotten entries only:
        forgotten and superseded entries are not observable there (None, not
        0). What it does show is how many entries are a later version."""
        mems = self._memories()
        return {"memories_latest": len(mems),
                "memories_forgotten": None,
                "superseded_live": None,
                "relation_updates": sum(1 for m in mems if (m.get("version") or 1) > 1),
                "history_versions": sum(len(m.get("history") or []) for m in mems),
                "static": sum(1 for m in mems if m.get("isStatic"))}

    def event_date_share(self) -> tuple[int, int]:
        mems = [m for m in self._memories() if not m.get("isForgotten")]
        dated = sum(1 for m in mems if self._when(m))
        return (dated, len(mems))

    # ── episodes and time ─────────────────────────────────────────────────
    @staticmethod
    def _doc_day(doc: dict) -> str:
        tc = (doc.get("metadata") or {}).get("temporalContext") or {}
        return str(tc.get("documentDate") or "")[:10]

    def _episodes(self) -> list[dict]:
        return [d for d in self._documents(content=True) if (d.get("metadata") or {}).get("kind") == "episode"]

    @staticmethod
    def _split(content: str) -> tuple[str, str]:
        user, _, rest = (content or "").partition("\nassistant: ")
        return user.removeprefix("user: "), rest

    def recent_days(self, n: int) -> list[str]:
        days = {self._doc_day(d) for d in self._episodes()}
        return sorted((d for d in days if _ISO.match(d)), reverse=True)[:n]

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        out = []
        for d in self._episodes():
            if self._doc_day(d) == day:
                inp, outp = self._split(str(d.get("content") or ""))
                out.append({"created_at": self._doc_day(d), "input_summary": inp, "output_summary": outp})
        return out[:limit]

    def signed_episodes(self, prefix: str) -> int:
        return sum(1 for d in self._episodes() if self._split(str(d.get("content") or ""))[0].startswith(prefix))

    # ── live state: direct memories, backing document deleted on overwrite ─
    def _delete_document(self, doc_id: str) -> bool:
        """Hard-delete a document and the entries extracted from it. A 404 is
        a removal only when this adapter already deleted that id."""
        try:
            self._req("DELETE", f"/v3/documents/{doc_id}")
        except SupermemoryError as e:
            return "HTTP 404" in str(e) and doc_id in self._deleted
        self._deleted.add(doc_id)
        self._pending = [i for i in self._pending if i != doc_id]
        return True

    def _drop_live(self, memory_id: str) -> bool:
        doc = self._live_docs.pop(memory_id, None)
        if doc and self._delete_document(doc):
            self._live_stats["hard_deleted"] += 1
            return True
        if self._forget_entry(memory_id):
            self._live_stats["soft_forgotten"] += 1
            return True
        self._live_stats["failed"] += 1
        return False

    def _forget_entry(self, memory_id: str) -> bool:
        try:
            d = self._req("DELETE", "/v4/memories", {"id": memory_id, "containerTag": self.container})
        except SupermemoryError as e:
            if "HTTP 409" in str(e):     # already forgotten
                return True
            return False
        return bool(d.get("forgotten"))

    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool:
        old = self._live.pop((session, key), None)
        if old:
            self._drop_live(old)
        d = self._req("POST", "/v4/memories",
                      {"containerTag": self.container, "memories": [{"content": f"{key}: {value}"}]})
        mems = d.get("memories") or []
        mid = mems[0].get("id") if mems and isinstance(mems[0], dict) else None
        if mid:
            self._live[(session, key)] = mid
            self._live_docs[mid] = d.get("documentId")
            self._live_stats["written"] += 1
        return bool(mid)

    def working_read(self, session: str, key: str):
        mid = self._live.get((session, key))
        if not mid:
            return None
        for m in self._memories():
            if m.get("id") == mid and not m.get("isForgotten"):
                text = str(m.get("memory") or "")
                return text.split(": ", 1)[1] if ": " in text else text
        return None

    def working_clear(self, session: str) -> None:
        for (s, k), mid in list(self._live.items()):
            if s == session:
                self._drop_live(mid)
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
        measures: dict = {"setup": dict(SETUP), "container": self.container}
        warnings: list[str] = []
        try:
            docs = self._documents()
            by_status: dict[str, int] = {}
            for d in docs:
                by_status[str(d.get("status"))] = by_status.get(str(d.get("status")), 0) + 1
            measures["documents"] = len(docs)
            measures["documents_by_status"] = by_status
            measures.update(self.update_trace())
        except SupermemoryError as e:
            warnings.append(str(e)[:160])
        if self._settles:
            s = sorted(self._settles)
            measures["settle_waits_s"] = s
            measures["settle_wait_p50_s"] = s[len(s) // 2]
            warnings.append(f"every write_fact/ingest_exchange/import waited for extraction before the door was "
                            f"asked (settle): p50 {s[len(s) // 2]} s, max {s[-1]} s. The serve times in the "
                            f"updates and write-back sections start after that wait")
        if self._unsettled:
            n = sum(len(x) for x in self._unsettled)
            measures["settles_timed_out"] = len(self._unsettled)
            warnings.append(f"{len(self._unsettled)} settle waits ended with {n} documents still not processed "
                            f"after {self.settle_max_s:.0f} s: the door was asked before extraction finished")
        if self._live_stats["written"]:
            ls = dict(self._live_stats)
            # entries written and not hard-deleted, minus the ones still live now
            ls["residue"] = ls["written"] - ls["hard_deleted"] - len(self._live_docs)
            measures["live_state_writes"] = ls
            if ls["residue"]:
                warnings.append(f"live state left {ls['residue']} entries in the store ({ls['soft_forgotten']} "
                                f"soft-forgotten, {ls['failed']} not removed): no backing document to delete")
        measures["update_trace_note"] = ("memories_forgotten and superseded_live are not observable: the list "
                                         "endpoint returns only the latest, non-forgotten entries")
        warnings.append("cards, files and graph edges are not exposed by the API: those sections are SKIP")
        return measures, warnings

    def measured_doors(self) -> list[str]:
        return ["POST /v4/search", "POST /v4/profile"]

    def traces(self) -> list[dict]:
        return list(self._traces)

    def probe_doors(self, questions: list[str]) -> None:
        for q in questions[:3]:
            for door in ("hybrid", "profile"):
                try:
                    self._answer(q, door)
                except SupermemoryError:
                    pass

    # ── optional ──────────────────────────────────────────────────────────
    def stored_mentions(self, phrase: str) -> int:
        low = phrase.lower()
        n = sum(1 for m in self._memories() if low in str(m.get("memory") or "").lower())
        n += sum(1 for d in self._documents(content=True) if low in str(d.get("content") or "").lower())
        return n

    def write_fact(self, text: str):
        return self.add_document(text)

    def import_memory(self, text: str, written_at: str):
        """The historical backfill path (batch with documentDate). An import is
        asynchronous in supermemory; it returns once the document is processed
        (the wait is counted in the settle measures)."""
        ids = self.add_batch([{"content": text, "documentDate": _iso(written_at)}])
        if ids:
            self.settle()
        return ids[0] if ids else None

    def ingest_exchange(self, question: str, answer: str):
        return self.add_document(f"user: {question}\nassistant: {answer}", kind="episode")

    def forget_memory(self, memory_id: str) -> bool:
        """Remove a document written by a probe, and the entries extracted
        from it (hard delete). A live-state entry goes with its backing
        document. A 404 is a removal only for an id already deleted here:
        a wrong id is a failed cleanup, not a success."""
        if memory_id in self._live_docs:
            self._live = {k: v for k, v in self._live.items() if v != memory_id}
            return self._drop_live(memory_id)
        return self._delete_document(memory_id)

    def declared_bytes(self) -> int | None:
        return None
