"""Adapter for mem0 (github.com/mem0ai/mem0): the open-source `mem0ai` library,
"a universal memory layer for AI agents", in its local form: no mem0 platform,
no mem0 account. At write time an LLM extracts memories from the messages
(ADD-only since mem0 2.x: new memories are added and linked, old ones are not
rewritten); at read time `search` scores them by vector similarity, BM25 and
entity boosts.

Measured with Gemini, through mem0's own providers:
  llm            provider "gemini", model gemini-3-flash-preview, max_tokens
                 8192 (mem0's defaults otherwise: temperature 0.1, top_p 0.1).
                 mem0's default max_tokens, 2000, counts Gemini 3's thinking
                 tokens too: in trial imports 1 and 3 of 21 extractions were
                 cut there, their JSON unparsable, the item silently lost.
                 MEM0_LLM_MAX_TOKENS sets it
  embedder       provider "gemini", models/gemini-embedding-001, 768 dims
  vector store   Qdrant, local on disk (<store>/qdrant), with mem0's BM25
                 slot (fastembed Qdrant/bm25) and its entity collection
  nlp            spaCy en_core_web_sm (mem0ai[nlp]), for BM25 lemmas and the
                 entity links
  history        SQLite at <store>/history.db
The key is GOOGLE_API_KEY, read inside the bridge. Every other cloud key is
removed from mem0's process (mem0 defaults to OpenAI: nothing can fall back to
it) and telemetry is off (MEM0_TELEMETRY=False before the import).

mem0 is a Python library with its own dependencies. adebench does not import
it: this adapter starts `adebench/mem0_bridge.py` with mem0's own Python and
talks to it in JSON lines, the Jev-Mem and cognee pattern.

    uv venv --python 3.11 .venv
    uv pip install --python .venv/Scripts/python.exe "mem0ai[nlp]" google-genai fastembed \\
        en_core_web_sm@https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
    MEM0_HOME=... MEM0_PYTHON=.../.venv/Scripts/python.exe python examples/mem0_import.py
    (re-import before EACH run: mem0 keeps the session's saved messages, and
    the next m.add reads them, so a run's probes would feed the next run)
    ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.mem0:Mem0Adapter \\
        --cases examples/synthetic_data/cases --no-sandbox-test --write-back

    MEM0_HOME        the directory of the mem0 install (its venv)
    MEM0_PYTHON      the Python of mem0's environment
    MEM0_STORE       where mem0 keeps everything: MEM0_DIR, Qdrant, history
                     (default <MEM0_HOME>/adebench_store; never ~/.mem0);
                     fastembed's BM25 model is cached next to it, in
                     <MEM0_STORE>/../fastembed_cache
    MEM0_USER_ID     the user_id measured (default adebench)
    MEM0_LLM_MODEL   default gemini-3-flash-preview
    MEM0_EMBED_MODEL default models/gemini-embedding-001 (MEM0_EMBED_DIMS 768)
    GOOGLE_API_KEY   the Gemini key, read by the bridge from its environment
    ADEBENCH_MEM0_TOP_K  results asked of search (default 20, mem0's own default)
    ADEBENCH_MEM0_CUT    a character cut on the door (default none)

Doors:
  search  what Memory.search returns for the question, filtered on the
          user_id, in mem0's order (its threshold 0.1 applies), rendered
          minimally: one line per result, its `memory` text, then the
          `metadata` mem0 returned with it as JSON when there is any (the
          writer's date and kind). Nothing else is added: an undated memory
          carries no date, and mem0's created_at (the time of the write) is
          not shown as an age. No cut.

What maps and what does not (SKIP is honest, not a zero):
  cards          none: mem0 stores extracted memories, not entity cards.
                 Corrections, aliases: none (an alias is written as a sentence)
  fact updates   mem0 2.x extraction is ADD-only: a changed value becomes a new
                 memory, linked, not a replacement (m.update exists, but only
                 when the client names the id). The harness probe runs through
                 write_fact (m.add, infer=True) and forget_memory (m.delete)
  time           mem0 OSS has no event time: `timestamp` on add is platform-only
                 (it raises in OSS) and the extraction prompt is given today as
                 its Observation Date. A memory's own date is carried in
                 metadata {"date"} and comes back with every hit; the day filter
                 is done in the adapter on get_all, episodes only (kind
                 episode; mem0 has no day query). Signed episodes are counted
                 on mem0's saved messages, the only text it keeps verbatim
  live state     a key is one m.add "key: value" (infer=True) scoped to the
                 session as run_id; replaced by deleting the memories the last
                 write produced and adding again; seen at the door when a hit
                 is one of them
  forget         m.delete removes the memory, its vector and its entity links,
                 not the session's saved messages: the next m.add in the same
                 scope reads the last messages again and can extract a
                 forgotten fact anew (seen in the write-back probe)
  wording        what reaches the door is mem0's rewording, not the text given:
                 a check that looks for the given text verbatim (the import
                 canary's "<token>:") does not find it. A FAIL of mem0's
                 extraction, not of the adapter
  empty writes   an m.add whose extraction stores nothing (mem0's dedup, or
                 nothing worth keeping) is mem0's answer, not an error: the
                 probes get a "mem0-nothing-stored:N" receipt, forget accepts
                 it, and the door shows the consequence
  files          not mapped: SKIP
  graph          mem0's entity collection: entities linked to memory ids.
                 Entity-link cleanup (the harness's orphan case): entities still
                 linking a memory that no longer exists; report-only, since with
                 no entity cards no edge case runs. Entity edges: SKIP
  declared bytes mem0's MCP server (OpenMemory) is a separate service, not
                 installed here: not measured
"""
from __future__ import annotations

import atexit
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from adebench.ade import competing_payload
from adebench.config import CFG

HOME = os.environ.get("MEM0_HOME", "")
PY = os.environ.get("MEM0_PYTHON", "")
STORE = os.environ.get("MEM0_STORE", "") or (str(Path(HOME) / "adebench_store") if HOME else "")
DOORS = ("search",)
NOOP = "mem0-nothing-stored:"   # the receipt of an m.add that stored no memory
_STOP = {"what", "which", "who", "when", "where", "does", "is", "the", "how", "many", "much", "about",
         "with", "for", "and", "that", "this", "are", "was", "were", "have", "has", "did"}
# removed from the bridge's environment; GOOGLE_API_KEY is passed through
# (inherited, never on a command line) and read by the bridge alone
_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "LLM_API_KEY", "AZURE_OPENAI_API_KEY",
         "MISTRAL_API_KEY", "GROQ_API_KEY", "TOGETHER_API_KEY", "DEEPSEEK_API_KEY", "XAI_API_KEY",
         "OPENAI_BASE_URL", "MEM0_API_KEY")


class Mem0Error(RuntimeError):
    pass


class _Bridge:
    def __init__(self) -> None:
        if not HOME or not PY:
            raise Mem0Error("set MEM0_HOME (the mem0 install) and MEM0_PYTHON (its Python)")
        env = {k: v for k, v in os.environ.items() if k not in _KEYS}
        env.update(MEM0_HOME=HOME, MEM0_STORE=STORE, MEM0_TELEMETRY="False", PYTHONIOENCODING="utf-8",
                   PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        Path(STORE).parent.mkdir(parents=True, exist_ok=True)
        self.log = open(Path(STORE).parent / "mem0_bridge.log", "a", encoding="utf-8")
        self.p = subprocess.Popen([PY, "-m", "adebench.mem0_bridge"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=self.log, env=env,
                                  text=True, encoding="utf-8", bufsize=1)
        self.lock = threading.Lock()
        # the bridge holds the store's files: wait for it to exit with us, so
        # that the next import can empty the store
        atexit.register(self.close)
        self.info = self.call("init")

    def call(self, op: str, **kw) -> dict:
        with self.lock:
            if self.p.poll() is not None:
                raise Mem0Error(f"bridge exited with code {self.p.returncode}")
            self.p.stdin.write(json.dumps({"op": op, **kw}) + "\n")
            self.p.stdin.flush()
            line = self.p.stdout.readline()
        if not line:
            raise Mem0Error(f"{op}: no answer from the bridge")
        d = json.loads(line)
        if not d.get("ok") and op != "delete":
            raise Mem0Error(f"{op}: {d.get('error')}")
        return d

    def close(self) -> None:
        if self.p.poll() is not None:
            return
        try:
            self.p.stdin.close()
            self.p.wait(timeout=30)
        except Exception:  # noqa: BLE001
            self.p.kill()


def hit_line(h: dict) -> str:
    """One search result as the door delivers it: mem0's `memory` text, then
    the `metadata` mem0 returned with it, as JSON, when there is any. Nothing
    is added: an undated memory carries no date (mem0's created_at is the
    time of the write, not the memory's age, and is not shown)."""
    text = str(h.get("memory") or "").strip()
    meta = h.get("metadata") or {}
    return f"{text} metadata={json.dumps(meta, ensure_ascii=False)}" if meta else text


def count_signed(messages: list[dict], prefix: str) -> int:
    """User messages, as mem0 saved them, that start with a machine signature."""
    return sum(1 for m in messages
               if m.get("role") == "user" and str(m.get("content") or "").startswith(prefix))


class Mem0Adapter:
    def __init__(self) -> None:
        self.top_k = int(os.environ.get("ADEBENCH_MEM0_TOP_K", "20"))
        self.cut = int(os.environ.get("ADEBENCH_MEM0_CUT", "0"))
        self._b: _Bridge | None = None
        self._traces: list[dict] = []
        self._live: dict[tuple[str, str], list[str]] = {}
        self._live_at: dict[tuple[str, str], float] = {}
        self.last_add: dict = {}

    def _bridge(self) -> _Bridge:
        if self._b is None:
            self._b = _Bridge()
        return self._b

    def _call(self, op: str, **kw) -> dict:
        return self._bridge().call(op, **kw)

    # ── writing ───────────────────────────────────────────────────────────
    def add(self, messages, metadata: dict | None = None, run_id: str | None = None) -> list[str]:
        """m.add with infer=True (mem0's normal path): the ids of the memories
        its extraction produced, possibly none."""
        d = self._call("add", messages=messages, metadata=metadata or {}, run_id=run_id, infer=True)
        self.last_add = d
        return [r["id"] for r in d.get("results", []) if r.get("id") and r.get("event") == "ADD"]

    def delete(self, memory_id: str) -> bool:
        return bool(self._call("delete", id=memory_id).get("ok"))

    def rows(self) -> list[dict]:
        return self._call("all")["rows"]

    def stats(self) -> dict:
        d = dict(self._call("stats"))
        d.pop("ok", None)
        return d

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        try:
            h = self._call("health")
        except (Mem0Error, OSError):
            return False
        return h.get("points", 0) > 0 and h.get("embedding_dims", 0) > 0

    def warm_up(self) -> float | None:
        t0 = time.perf_counter()
        try:
            self._call("search", q="hello", top_k=1)
        except Mem0Error:
            return None
        return (time.perf_counter() - t0) * 1000

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return list(DOORS)

    def door_cut(self, door: str) -> int | None:
        return self.cut or None

    def _search(self, query: str, top_k: int | None = None) -> dict:
        t0 = time.perf_counter()
        failed, chars = False, 0
        try:
            d = self._call("search", q=query, top_k=top_k or self.top_k)
            chars = sum(len(h.get("memory") or "") for h in d.get("hits", []))
            return d
        except Mem0Error:
            failed = True
            raise
        finally:
            self._traces.append({"door": "search", "ms": (time.perf_counter() - t0) * 1000,
                                 "chars": chars, "http": 500 if failed else 200})

    def _answer(self, query: str) -> dict:
        hits = self._search(query).get("hits", [])
        live = {mid: k for (_s, k), ids in self._live.items() for mid in ids}
        semantic, episodic, working, lines = [], [], [], []
        for h in hits:
            line = hit_line(h)
            lines.append(line)
            meta = h.get("metadata") or {}
            if meta.get("kind") == "episode":
                episodic.append({"created_at": meta.get("date"), "input_summary": h.get("memory"),
                                 "output_summary": ""})
            else:
                semantic.append({"source": "mem0:memory", "content": line, "key": h.get("id"),
                                 "_score": h.get("score")})
            if h.get("id") in live:
                # a live-state memory is whatever mem0 extracted from "key: value":
                # the value is its whole text, as mem0 worded it
                working.append({"key": live[h["id"]], "value": str(h.get("memory") or "")})
        summary = "\n".join(lines)
        unknown = []
        if not hits:
            # nothing above mem0's threshold: its abstention, passed on as unknown terms
            summary = "search: no results"
            unknown = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", query) if w.lower() not in _STOP][:3]
        return {"summary": summary, "semantic": semantic, "cards": [], "episodic": episodic, "working": working,
                "unknown_terms": unknown, "_raw": [{k: h.get(k) for k in ("id", "score")} for h in hits]}

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
    def update_trace(self) -> dict:
        ev = self._call("history_counts").get("events") or {}
        # ADD-only extraction: an UPDATE in mem0's history only comes from an
        # m.update(id, ...) a client made
        return {"superseded_live": 0, "relation_updates": int(ev.get("UPDATE") or 0), "history_events": ev}

    def event_date_share(self) -> tuple[int, int]:
        rs = self.rows()
        return (sum(1 for r in rs if (r.get("metadata") or {}).get("date")), len(rs))

    # ── episodes and time ─────────────────────────────────────────────────
    @staticmethod
    def _date(r: dict) -> str:
        return str((r.get("metadata") or {}).get("date") or "")

    def _episodes(self) -> list[dict]:
        """The memories mem0 extracted from an episode, with the episode's date."""
        return [r for r in self.rows()
                if (r.get("metadata") or {}).get("kind") == "episode" and self._date(r)]

    def recent_days(self, n: int) -> list[str]:
        days = {self._date(r)[:10] for r in self._episodes()}
        return sorted(days, reverse=True)[:n]

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        out = [{"created_at": self._date(r), "input_summary": r.get("memory"), "output_summary": ""}
               for r in self._episodes() if self._date(r)[:10] == day]
        return out[:limit]

    def signed_episodes(self, prefix: str) -> int:
        """Counted on what mem0 keeps verbatim, its saved messages (the last 10
        per session scope), not on the reworded memories."""
        return count_signed(self._call("messages").get("messages", []), prefix)

    # ── live state: add (run_id = session) / delete ───────────────────────
    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool:
        for mid in self._live.pop((session, key), []):
            self.delete(mid)
        ids = self.add(f"{key}: {value}", metadata={"kind": "live"}, run_id=session)
        if not ids:
            return False   # the extraction kept nothing: the write did not happen
        self._live[(session, key)] = ids
        self._live_at[(session, key)] = time.time()
        return True

    def working_read(self, session: str, key: str):
        ids = self._live.get((session, key))
        if not ids:
            return None
        texts = []
        for mid in ids:
            row = self._call("get", id=mid).get("row")
            if row and row.get("memory"):
                texts.append(str(row["memory"]))
        return " ".join(texts) or None

    def working_clear(self, session: str) -> None:
        for (s, k), ids in list(self._live.items()):
            if s == session:
                for mid in ids:
                    self.delete(mid)
                self._live.pop((s, k), None)
                self._live_at.pop((s, k), None)

    def working_age_minutes(self, session: str, key: str) -> float | None:
        t = self._live_at.get((session, key))
        return (time.time() - t) / 60 if t else None

    # ── files: none; graph: mem0's entity links ───────────────────────────
    def file_search(self, query: str, limit: int) -> list[str]:
        return []

    def graph_edges(self, entity: str) -> int:
        return int(self._call("entities", entity=entity).get("entity_links") or 0)

    def graph_orphans(self) -> tuple[int, int]:
        e = self._call("entities")
        return (int(e.get("entities_with_dangling_links") or 0), int(e.get("entities") or 0))

    def graph_counts(self) -> dict:
        e = self._call("entities")
        return {"nodes": e.get("entities"), "edges": e.get("links"), "dangling_links": e.get("dangling_links"),
                "entities_by_type": e.get("entities_by_type"), "memories": e.get("memories")}

    # ── report-only ───────────────────────────────────────────────────────
    def health_report(self) -> tuple[dict, list[str]]:
        info = dict(self._bridge().info)
        info.pop("ok", None)
        measures: dict = {"bridge": info, "top_k": self.top_k}
        warnings = ["no entity cards and no files: those sections are SKIP; mem0 OSS has no event time "
                    "(timestamp is platform-only): dates come from the metadata the writer gave"]
        try:
            h = self._call("health")
            h.pop("ok", None)
            measures["health"] = h
        except Mem0Error as e:
            warnings.append(str(e)[:160])
        try:
            measures["calls"] = self.stats()
        except Mem0Error:
            pass
        return measures, warnings

    def measured_doors(self) -> list[str]:
        return list(DOORS)

    def traces(self) -> list[dict]:
        return list(self._traces)

    def probe_doors(self, questions: list[str]) -> None:
        return None

    # ── optional ──────────────────────────────────────────────────────────
    def stored_mentions(self, phrase: str) -> int:
        low = phrase.lower()
        return sum(1 for r in self.rows() if low in str(r.get("memory") or "").lower())

    # A write through m.add can store nothing: the extraction found nothing new
    # (mem0's own dedup) or nothing worth keeping. That is mem0's answer, not
    # a failed call, so the probes get a receipt for it, NOOP + a counter,
    # which forget_memory accepts (there is nothing to remove) and the door
    # then shows the consequence.
    def _receipt(self, ids: list[str]):
        if ids:
            return ids
        self._noop = getattr(self, "_noop", 0) + 1
        return [f"{NOOP}{self._noop}"]

    def write_fact(self, text: str):
        return self._receipt(self.add(text, metadata={"kind": "fact"}))

    def forget_memory(self, memory_id: str) -> bool:
        if str(memory_id).startswith(NOOP):
            return True
        return self.delete(memory_id)

    def import_memory(self, text: str, written_at: str):
        return self._receipt(self.add(text, metadata={"date": written_at, "kind": "imported"}))

    def ingest_exchange(self, question: str, answer: str):
        return self._receipt(self.add([{"role": "user", "content": question},
                                       {"role": "assistant", "content": answer}],
                                      metadata={"kind": "conversation"}))

    def settle(self) -> None:
        return None   # m.add is synchronous: stored and indexed when it returns

    def declared_bytes(self) -> int | None:
        return None
