"""Adapter for cognee (github.com/topoteretes/cognee): an "AI memory platform"
that turns what it is given into a knowledge graph (documents, chunks,
entities, typed relations) plus a vector index over chunks, summaries and
entities, in Python.

Two modes (COGNEE_LLM):
  gemini (default)  cognee's normal, LLM-based mode, set up as its docs say:
                    LLM_PROVIDER=gemini, LLM_MODEL=gemini/gemini-3-flash-preview
                    (extraction, summaries, answers), embeddings
                    gemini/gemini-embedding-001 at 768 dimensions. The key is
                    GOOGLE_API_KEY, passed in the inherited environment and moved
                    by the bridge to LLM_API_KEY / EMBEDDING_API_KEY. This is the
                    published reference (examples/cognee_report/reference.*).
  gliner_demo       the local no-key mode: cognee's GLiNER *demo* extractor
                    (`cognee[gliner]`), fastembed BAAI/bge-small-en-v1.5 on CPU.
                    A demo, not cognee's normal mode: kept for the record in
                    examples/cognee_report/reference_gliner_demo.*, not published.
Both: LanceDB for vectors, Ladybug for the graph, SQLite for the metadata,
telemetry off, every other cloud key removed from cognee's process.

cognee is a Python library with heavy dependencies (torch, lancedb, litellm).
adebench does not import it: this adapter starts `adebench/cognee_bridge.py`
with cognee's own Python and talks to it in JSON lines, the Jev-Mem pattern.
The bridge was chosen over cognee's REST server because it needs no server
process, no auth user and no port, and reaches the same SDK calls
(add, cognify, recall, forget, datasets.list_data, the graph engine). In
Gemini mode it also counts every litellm call and its tokens
(COGNEE_HOME/cognee_usage/, one file per bridge process).

    uv venv --python 3.11 .venv && uv pip install --python .venv/Scripts/python.exe "cognee[gliner]"
    COGNEE_HOME=... COGNEE_PYTHON=.../.venv/Scripts/python.exe python examples/cognee_import.py
    ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.cognee:CogneeAdapter \\
        --cases sets/quick/cases --no-sandbox-test --write-back

    COGNEE_LLM     gemini (default) | gliner_demo
    COGNEE_HOME     the directory of the cognee install (its venv)
    COGNEE_PYTHON   the Python of cognee's environment
    COGNEE_STORE    where cognee keeps data, databases, cache and logs
                    (default <COGNEE_HOME>/adebench_store_<mode>; never the home default)
    COGNEE_DATASET  the dataset measured (default adebench)
    COGNEE_LLM_MODEL / COGNEE_EMBEDDING_MODEL  override the Gemini models
    GOOGLE_API_KEY  Gemini mode only
    ADEBENCH_COGNEE_TOP_K  hits asked of recall on the chunk doors (default 15,
                    cognee's own default)
    ADEBENCH_COGNEE_CUT    a character cut on the door (default none)

Doors, Gemini mode:
  context        cognee.recall with cognee's own routing (no query type; it
                 picks HYBRID_COMPLETION) and only_context=True: the text its
                 answer model receives, as delivered (the question, the
                 passages, the entities, the related facts). The
                 passages carry their date through cognee's own opt-in
                 (retriever_specific_config include_external_metadata, key
                 'date'). No answer model runs on this door. No cut.
  answer         the same call without only_context: Gemini's composed answer.
                 Measured on the side (probe_doors); --door answer to score it.
  chunks         CHUNKS: the vector hits alone, as in the keyless mode.
Doors, gliner_demo mode:
  recall         cognee.recall with no query type: keyless, cognee itself picks
                 CHUNKS. One line per hit; the date in front is the hit's
                 external_metadata date; an undated item carries none (its
                 storage time is never shown as its age).
  graph_context  GRAPH_COMPLETION with only_context=True, on the side.

What maps and what does not (SKIP is honest, not a zero):
  cards          none: cognee has Entity nodes, not entity cards. Corrections,
                 aliases: none (an alias is written as a sentence)
  fact updates   cognee does not supersede by default (functional_relationships
                 and contradiction detection are opt-in). The harness probe runs
                 through write_fact (add + cognify) and forget_memory (forget by
                 data_id)
  time           a memory's date goes in DataItem.external_metadata {"date"}
                 and comes back with the passage / hit; the day filter is done in
                 the adapter on datasets.list_data (cognee has no day query)
  live state     a key is one data item "key: value", replaced by forget and a
                 new add + cognify; seen at the door when a passage carries it
  session        cognee's session memory is on by default; every recall gets a
                 fresh session_id, so no earlier question or answer of the run
                 (or of an earlier run on the same store) comes back
  files          not mapped: SKIP
  graph          the real graph, report-only here: the orphan check covers chunk
                 hygiene only (chunk nodes whose data item is gone after forget),
                 not entity quality; counts by node type and relation. Entity
                 edges are asked only for entities with a card: none, SKIP
  declared bytes cognee's MCP server (cognee-mcp) is a separate package, not
                 installed here: not measured
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from adebench.ade import competing_payload
from adebench.config import CFG

HOME = os.environ.get("COGNEE_HOME", "")
PY = os.environ.get("COGNEE_PYTHON", "")
MODE = os.environ.get("COGNEE_LLM", "gemini").lower()
MODE = "gliner_demo" if MODE in ("gliner", "local") else MODE
STORE = os.environ.get("COGNEE_STORE", "") or (str(Path(HOME) / f"adebench_store_{MODE}") if HOME else "")
DATASET = os.environ.get("COGNEE_DATASET", "adebench")
DOORS = ("context", "answer", "chunks") if MODE == "gemini" else ("recall", "graph_context")
_STOP = {"what", "which", "who", "when", "where", "does", "is", "the", "how", "many", "much", "about",
         "with", "for", "and", "that", "this", "are", "was", "were", "have", "has", "did"}
_KEYS = ("LLM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
         "EMBEDDING_API_KEY", "AZURE_OPENAI_API_KEY", "MISTRAL_API_KEY", "GROQ_API_KEY")


class CogneeError(RuntimeError):
    pass


class _Bridge:
    def __init__(self, fresh: bool = False) -> None:
        if not HOME or not PY:
            raise CogneeError("set COGNEE_HOME (the cognee install) and COGNEE_PYTHON (its Python)")
        # Gemini mode passes GOOGLE_API_KEY through the inherited environment
        # (never the command line); the bridge moves it to cognee's own
        # variables. Every other cloud key is dropped; in gliner_demo mode all are.
        keep = {"GOOGLE_API_KEY"} if MODE == "gemini" else set()
        env = {k: v for k, v in os.environ.items() if k not in _KEYS or k in keep}
        env.update(COGNEE_LLM=MODE, COGNEE_HOME=HOME, COGNEE_STORE=STORE, COGNEE_DATASET=DATASET, PYTHONIOENCODING="utf-8",
                   PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        self.log = open(Path(STORE).parent / "cognee_bridge.log", "a", encoding="utf-8") \
            if Path(STORE).parent.is_dir() else subprocess.DEVNULL
        self.p = subprocess.Popen([PY, "-m", "adebench.cognee_bridge"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=self.log, env=env,
                                  text=True, encoding="utf-8", bufsize=1)
        self.lock = threading.Lock()
        self.info = self.call("init", fresh=fresh)

    def call(self, op: str, **kw) -> dict:
        with self.lock:
            if self.p.poll() is not None:
                raise CogneeError(f"bridge exited with code {self.p.returncode}")
            self.p.stdin.write(json.dumps({"op": op, **kw}) + "\n")
            self.p.stdin.flush()
            line = self.p.stdout.readline()
        if not line:
            raise CogneeError(f"{op}: no answer from the bridge")
        d = json.loads(line)
        if not d.get("ok") and op != "forget":
            raise CogneeError(f"{op}: {d.get('error')}")
        return d

    def close(self) -> None:
        try:
            self.p.stdin.close()
            self.p.wait(timeout=30)
        except Exception:  # noqa: BLE001
            self.p.kill()


_ABS_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|file:///|/(?:home|Users|root|tmp|var)/)[^\s'\"]*")


def _no_paths(v):
    """Reports carry no absolute personal path: a path becomes its last part."""
    if isinstance(v, str):
        return _ABS_PATH.sub(lambda m: "<path>/" + re.split(r"[\\/]", m.group(0).rstrip("\\/"))[-1], v)
    if isinstance(v, dict):
        return {k: _no_paths(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_no_paths(x) for x in v]
    return v


_PASSAGES = re.compile(r"## Relevant passages\n(.*?)(?=\n## |`?\s*$)", re.S)


def passages(context: str) -> list[tuple[str, str]]:
    """(date, text) of each passage in cognee's hybrid context, as delivered:
    the passages under '## Relevant passages', separated by '---', each with a
    'date: ...' line above it when the memory was given one."""
    m = _PASSAGES.search(context or "")
    if not m:
        return []
    out = []
    for block in m.group(1).split("\n---\n"):
        block = block.strip().rstrip("`").strip()
        date = ""
        if block.startswith("date: "):
            first, _, block = block.partition("\n")
            date = first[6:].strip()
        if block:
            out.append((date, block.strip()))
    return out


def hit_line(h: dict) -> str:
    """One recall hit as the door delivers it: the date it carries, then its text."""
    text = str(h.get("text") or "").strip()
    date = str((h.get("external_metadata") or {}).get("date") or "")
    if date:
        return f"[{date}] {text}"
    return text   # undated: the storage time is not the memory's age


class CogneeAdapter:
    def __init__(self, fresh: bool = False) -> None:
        self.fresh = fresh
        self.top_k = int(os.environ.get("ADEBENCH_COGNEE_TOP_K", "15"))
        self.cut = int(os.environ.get("ADEBENCH_COGNEE_CUT", "0"))
        self._b: _Bridge | None = None
        self._traces: list[dict] = []
        self._live: dict[tuple[str, str], str] = {}
        self._live_at: dict[tuple[str, str], float] = {}
        self._search_types: dict[str, int] = {}
        self._rows: list[dict] | None = None

    def _bridge(self) -> _Bridge:
        if self._b is None:
            self._b = _Bridge(fresh=self.fresh)
        return self._b

    def _call(self, op: str, **kw) -> dict:
        return self._bridge().call(op, **kw)

    # ── writing ───────────────────────────────────────────────────────────
    def add(self, items: list[dict], cognify: bool = True) -> list[str | None]:
        """items: [{text, meta: {date?, kind?}}] -> data ids, through cognee.add
        and then cognify (what remember() does without a session)."""
        self._rows = None
        return self._call("add", items=items, cognify=cognify)["ids"]

    def write(self, text: str, when: str | None = None, kind: str = "fact") -> str | None:
        return self.add([{"text": text, "meta": {"date": when, "kind": kind}}])[0]

    def delete(self, data_id: str) -> bool:
        self._rows = None
        return bool(self._call("forget", id=data_id).get("ok"))

    def rows(self) -> list[dict]:
        return self._call("rows")["rows"]

    def _rows_cached(self) -> list[dict]:
        if self._rows is None:
            self._rows = self.rows()
        return self._rows

    def usage(self) -> dict:
        return self._call("usage").get("usage") or {}

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        try:
            h = self._call("health")
        except (CogneeError, OSError):
            return False
        return h.get("status") == "healthy" and bool(h.get("dataset_exists"))

    def warm_up(self) -> float | None:
        t0 = time.perf_counter()
        try:
            self._call("recall", q="hello", top_k=1, door=DOORS[0] if DOORS[0] != "answer" else "context")
        except CogneeError:
            return None
        return (time.perf_counter() - t0) * 1000

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return list(DOORS)

    def door_cut(self, door: str) -> int | None:
        return self.cut or None

    def _recall(self, query: str, door: str) -> dict:
        t0 = time.perf_counter()
        failed, chars = False, 0
        try:
            d = self._call("recall", q=query, top_k=self.top_k, door=door)
            chars = sum(len(h.get("text") or "") for h in d.get("hits", []))
            return d
        except CogneeError:
            failed = True
            raise
        finally:
            self._traces.append({"door": door, "ms": (time.perf_counter() - t0) * 1000,
                                 "chars": chars, "http": 500 if failed else 200})

    def _answer(self, query: str, door: str = "recall") -> dict:
        d = self._recall(query, door)
        hits = d.get("hits", [])
        for h in hits:
            st = h.get("search_type") or "?"
            self._search_types[st] = self._search_types.get(st, 0) + 1
        if door in ("graph_context", "answer"):
            summary = "\n".join(h["text"] for h in hits).strip()
            return {"summary": summary or f"{door}: none", "semantic": [], "cards": [], "episodic": [],
                    "working": [], "unknown_terms": [], "_raw": {"search_types": [h.get("search_type") for h in hits]}}
        live = {v: k for k, v in self._live.items()}
        if door == "context":
            return self._context(query, hits, live)
        semantic, episodic, working, lines = [], [], [], []
        for h in hits:
            line = hit_line(h)
            lines.append(line)
            meta = h.get("external_metadata") or {}
            if meta.get("kind") == "episode":
                episodic.append({"created_at": meta.get("date"), "input_summary": h["text"], "output_summary": ""})
            else:
                # every CHUNKS hit is a nearest neighbour by meaning: cognee's
                # keyless recall has no keyword leg and no relevance floor
                semantic.append({"source": "semantic_vec:cognee_chunk", "content": line,
                                 "key": h.get("data_id"), "_score": h.get("score")})
            if h.get("data_id") in live and ": " in h["text"]:
                key, _, value = h["text"].partition(": ")
                working.append({"key": key, "value": value.strip()})
        summary = "\n".join(lines)
        unknown = []
        if not hits:
            summary = "recall: no results"
            unknown = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", query) if w.lower() not in _STOP][:3]
        return {"summary": summary, "semantic": semantic, "cards": [], "episodic": episodic, "working": working,
                "unknown_terms": unknown,
                "_raw": [{k: h.get(k) for k in ("data_id", "score", "search_type")} for h in hits]}

    def _context(self, query: str, hits: list[dict], live: dict) -> dict:
        """The context door: cognee's text as delivered; the passages in it are
        read back as semantic / episodic / working entries, matched to the
        stored items by their text."""
        summary = "\n".join(h["text"] for h in hits).strip()
        by_text = {str(r.get("text") or "").strip(): r for r in self._rows_cached()}
        semantic, episodic, working = [], [], []
        for date, text in passages(summary):
            row = by_text.get(text) or {}
            if (row.get("meta") or {}).get("kind") == "episode":
                episodic.append({"created_at": date, "input_summary": text, "output_summary": ""})
            else:
                # the passage lane of cognee's hybrid retrieval is a vector
                # search over chunks (top 5): neighbours by meaning
                semantic.append({"source": "semantic_vec:cognee_passage",
                                 "content": f"[{date}] {text}" if date else text, "key": row.get("id")})
            if row.get("id") in live and ": " in text:
                key, _, value = text.partition(": ")
                working.append({"key": key, "value": value.strip()})
        unknown = []
        if not summary:
            summary = "context: none"
            unknown = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", query) if w.lower() not in _STOP][:3]
        return {"summary": summary, "semantic": semantic, "cards": [], "episodic": episodic, "working": working,
                "unknown_terms": unknown, "_raw": {"search_types": [h.get("search_type") for h in hits]}}

    def door_text(self, query: str, door: str) -> tuple[str, dict]:
        if door not in DOORS:
            raise CogneeError(f"unknown door {door!r}: this mode has {', '.join(DOORS)}")
        r = self._answer(query, door)
        text = competing_payload(CFG.pressure) + r["summary"]
        return (text[:self.cut] if self.cut else text), r

    def ask(self, query: str) -> dict:
        return self._answer(query, DOORS[0])

    # ── cards, corrections, aliases: none ─────────────────────────────────
    def cards(self) -> list[dict]:
        return []

    def corrections(self) -> list[dict]:
        return []

    def aliases(self) -> list[dict]:
        return []

    # ── facts and their lifecycle ─────────────────────────────────────────
    def update_trace(self) -> dict:
        g = self._call("graph")
        return {"superseded_live": int(g.get("superseded_edges") or 0),
                "relation_updates": int(g.get("contradicts_edges") or 0),
                "edges_by_relationship": g.get("edges_by_relationship")}

    def event_date_share(self) -> tuple[int, int]:
        rs = self.rows()
        return (sum(1 for r in rs if (r.get("meta") or {}).get("date")), len(rs))

    # ── episodes and time ─────────────────────────────────────────────────
    @staticmethod
    def _date(r: dict) -> str:
        return str((r.get("meta") or {}).get("date") or "")

    def recent_days(self, n: int) -> list[str]:
        rs = [r for r in self.rows() if self._date(r)]
        eps = [r for r in rs if (r.get("meta") or {}).get("kind") == "episode"] or rs
        days = {self._date(r)[:10] for r in eps}
        return sorted((d for d in days if d), reverse=True)[:n]

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        out = []
        for r in self.rows():
            if self._date(r)[:10] == day:
                out.append({"created_at": self._date(r), "input_summary": r.get("text"), "output_summary": ""})
        return out[:limit]

    def signed_episodes(self, prefix: str) -> int:
        return sum(1 for r in self.rows() if str(r.get("text") or "").startswith(prefix))

    # ── live state: add / forget ──────────────────────────────────────────
    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool:
        old = self._live.pop((session, key), None)
        if old:
            self.delete(old)
        nid = self.write(f"{key}: {value}", kind="live")
        if not nid:
            return False
        self._live[(session, key)] = nid
        self._live_at[(session, key)] = time.time()
        return True

    def working_read(self, session: str, key: str):
        nid = self._live.get((session, key))
        if not nid:
            return None
        for r in self.rows():
            if r["id"] == nid:
                text = str(r.get("text") or "")
                return text.split(":", 1)[1].strip() if ":" in text else text
        return None

    def working_clear(self, session: str) -> None:
        for (s, k), nid in list(self._live.items()):
            if s == session:
                self.delete(nid)
                self._live.pop((s, k), None)
                self._live_at.pop((s, k), None)

    def working_age_minutes(self, session: str, key: str) -> float | None:
        t = self._live_at.get((session, key))
        return (time.time() - t) / 60 if t else None

    # ── files: none; graph: cognee's own ──────────────────────────────────
    def file_search(self, query: str, limit: int) -> list[str]:
        return []

    def graph_edges(self, entity: str) -> int:
        return int(self._call("entity_edges", entity=entity).get("edges") or 0)

    def graph_orphans(self) -> tuple[int, int]:
        g = self._call("graph")
        return (int(g.get("orphan_chunk_nodes") or 0), int(g.get("chunk_nodes") or 0))

    def graph_counts(self) -> dict:
        g = self._call("graph")
        return {k: g.get(k) for k in ("nodes", "edges", "nodes_by_type", "edges_by_relationship",
                                      "entities_without_edges", "data_items")}

    # ── report-only ───────────────────────────────────────────────────────
    def health_report(self) -> tuple[dict, list[str]]:
        info = dict(self._bridge().info)
        info.pop("ok", None)
        measures: dict = {"bridge": info, "search_types_seen": dict(self._search_types)}
        if MODE == "gemini":
            # the setup and the one non-default door option, in the report itself
            measures["setup"] = {
                "llm": info.get("llm"), "extractor": info.get("extractor"), "embedding": info.get("embedding"),
                "context_door": "cognee.recall, no query_type (cognee's routing), only_context=True, "
                                "retriever_specific_config={include_external_metadata: true, "
                                "external_metadata_keys: [date]} (non-default: puts each passage's date "
                                "in the context), a fresh session_id per call",
                "answer_door": "the same call without only_context: the LLM's answer",
                "chunks_door": f"query_type=CHUNKS, top_k={self.top_k}"}
        else:
            measures["setup"] = {"extractor": info.get("extractor"), "embedding": info.get("embedding"),
                                 "recall_door": f"cognee.recall, no query_type (keyless: CHUNKS), top_k={self.top_k}, "
                                                "a fresh session_id per call"}
        if MODE == "gemini":
            try:
                measures["llm_usage_this_run"] = self.usage()
            except CogneeError:
                pass
        warnings = ["no entity cards and no files: those sections are SKIP; cognee's chunk retrieval is a "
                    "vector search with no relevance floor: it always returns its top_k hits"]
        try:
            h = self._call("health")
            measures["health"] = {"status": h.get("status"), "components": h.get("components")}
            if h.get("status") != "healthy":
                warnings.append(f"cognee health: {h.get('status')}")
        except CogneeError as e:
            warnings.append(str(e)[:160])
        return _no_paths(measures), [_no_paths(w) for w in warnings]

    def measured_doors(self) -> list[str]:
        return list(DOORS)

    def traces(self) -> list[dict]:
        return list(self._traces)

    def probe_doors(self, questions: list[str]) -> None:
        for door in DOORS[1:]:
            for q in questions:
                try:
                    self._answer(q, door)
                except CogneeError:
                    pass

    # ── optional ──────────────────────────────────────────────────────────
    def stored_mentions(self, phrase: str) -> int:
        low = phrase.lower()
        return sum(1 for r in self.rows() if low in str(r.get("text") or "").lower())

    def write_fact(self, text: str):
        return self.write(text, kind="fact")

    def forget_memory(self, memory_id: str) -> bool:
        return self.delete(memory_id)

    def import_memory(self, text: str, written_at: str):
        return self.write(text, when=written_at, kind="imported")

    def ingest_exchange(self, question: str, answer: str):
        return self.write(f"User: {question}\nAssistant: {answer}", kind="conversation")

    def declared_bytes(self) -> int | None:
        return None
