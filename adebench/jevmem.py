"""Adapter for Jev-Mem (github.com/libingzheren/Jev-Mem): agentic memory whose
memory decisions (typing, relations, routing, stopping) are taken by a small
System-One model instead of an LLM, over a graph with semantic, temporal,
causal and entity relations.

Jev-Mem is a Python library with its own dependencies (torch, faiss,
sentence-transformers, the Laya or TypeSafe SDK). adebench does not import
it: this adapter starts `adebench/jevmem_bridge.py` with Jev-Mem's own Python
and talks to it in JSON lines, so the harness stays dependency-free and the
models are loaded once per run.

    git clone https://github.com/libingzheren/Jev-Mem && cd Jev-Mem
    python3.11 -m venv .venv && .venv/bin/pip install -e '.[laya]'
    JEVMEM_HOME=... JEVMEM_PYTHON=.../.venv/bin/python python examples/jevmem_import.py
    python -m adebench --adapter adebench.jevmem:JevMemAdapter --cases examples/synthetic_data/cases

    JEVMEM_HOME     the Jev-Mem checkout (its config/ and packages)
    JEVMEM_PYTHON   the Python of Jev-Mem's environment
    JEVMEM_STORE    where the memory is saved (default <JEVMEM_HOME>/adebench_store)
    JEVMEM_CONFIG   decision profile (default config/laya_mem.json: Laya, local,
                    no API key; config/jev_mem.json uses the TypeSafe Jev API)
    JEVMEM_DEVICE   Laya device: auto | cpu | cuda (default auto)
    ADEBENCH_JEVMEM_TOP_K  evidence items asked of the query engine (default 5,
                    the value JevMemSystem.query uses)

Doors:
  evidence  what QueryEngine.query returns for the question: the ranked
            evidence block System Two would answer from, each item with its
            date. No answer model runs (OPENAI_API_KEY is removed in the
            bridge): the benchmark measures what reaches the model. No cut.

What maps and what does not (SKIP is honest, not a zero):
  cards          none: the graph has event nodes, no entity cards. Corrections,
                 aliases: none (an alias is written as a sentence)
  fact updates   no supersede trace is exposed; contradiction and obsolescence
                 are link judgments at write time. The harness probe runs
                 through write_fact (build) and forget_memory
  forget         Jev-Mem has no forget: the adapter removes the node, its links,
                 its vector and its keyword-index entries, then saves
  time           every node carries its observation timestamp; the day filter
                 is done on the nodes in the adapter
  live state     a key is one observation "key: value", replaced by removal and
                 a new write; seen at the door when the evidence carries it
  files          none: SKIP
  graph          edges touching the nodes that name an entity
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

HOME = os.environ.get("JEVMEM_HOME", "")
PY = os.environ.get("JEVMEM_PYTHON", "")
STORE = os.environ.get("JEVMEM_STORE", "") or (str(Path(HOME) / "adebench_store") if HOME else "")
CONFIG = os.environ.get("JEVMEM_CONFIG", "config/laya_mem.json")
DEVICE = os.environ.get("JEVMEM_DEVICE", "auto")
DOORS = ("evidence",)
_ITEM = re.compile(r"^\s*\d+\.\s+(?:\*\*?[^*]+\*\*?\s+)?(?:\[([^\]]+)\]\s+)?(.+)$")
_STOP = {"what", "which", "who", "when", "where", "does", "is", "the", "how", "many", "much", "about",
         "with", "for", "and", "that", "this", "are", "was", "were", "have", "has", "did", "module", "service"}


class JevMemError(RuntimeError):
    pass


class _Bridge:
    def __init__(self, fresh: bool = False) -> None:
        if not HOME or not PY:
            raise JevMemError("set JEVMEM_HOME (the Jev-Mem checkout) and JEVMEM_PYTHON (its Python)")
        env = dict(os.environ, JEVMEM_HOME=HOME, PYTHONIOENCODING="utf-8", USE_TF="0",
                   PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        self.p = subprocess.Popen([PY, "-m", "adebench.jevmem_bridge"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env,
                                  text=True, encoding="utf-8", bufsize=1)
        self.lock = threading.Lock()
        self.info = self.call("init", cache_dir=STORE, config=CONFIG, device=DEVICE, fresh=fresh, timeout=900)

    def call(self, op: str, timeout: float = 600, **kw) -> dict:
        with self.lock:
            if self.p.poll() is not None:
                raise JevMemError(f"bridge exited with code {self.p.returncode}")
            self.p.stdin.write(json.dumps({"op": op, **kw}) + "\n")
            self.p.stdin.flush()
            line = self.p.stdout.readline()
        if not line:
            raise JevMemError(f"{op}: no answer from the bridge")
        d = json.loads(line)
        if not d.get("ok") and op != "delete":
            raise JevMemError(f"{op}: {d.get('error')}")
        return d

    def close(self) -> None:
        try:
            self.p.stdin.close()
            self.p.wait(timeout=20)
        except Exception:  # noqa: BLE001
            self.p.kill()


class JevMemAdapter:
    def __init__(self, fresh: bool = False) -> None:
        self.fresh = fresh
        self.top_k = int(os.environ.get("ADEBENCH_JEVMEM_TOP_K", "5"))
        self.cut = int(os.environ.get("ADEBENCH_JEVMEM_CUT", "0"))
        self._b: _Bridge | None = None
        self._traces: list[dict] = []
        self._live: dict[tuple[str, str], str] = {}
        self._live_at: dict[tuple[str, str], float] = {}
        self._node_cache: list[dict] | None = None

    def _bridge(self) -> _Bridge:
        if self._b is None:
            self._b = _Bridge(fresh=self.fresh)
        return self._b

    def _call(self, op: str, **kw) -> dict:
        t0 = time.perf_counter()
        failed = False
        try:
            return self._bridge().call(op, **kw)
        except JevMemError:
            failed = True
            raise
        finally:
            if op == "query":
                self._traces.append({"door": "evidence", "ms": (time.perf_counter() - t0) * 1000,
                                     "chars": 0, "http": 500 if failed else 200})

    # ── writing ───────────────────────────────────────────────────────────
    def build(self, items: list[dict], save: bool = True) -> list[str | None]:
        self._node_cache = None
        return self._call("build", items=items, save=save, timeout=3600)["ids"]

    def _nodes_cached(self) -> list[dict]:
        if getattr(self, "_node_cache", None) is None:
            self._node_cache = self.nodes()
        return self._node_cache

    def write(self, text: str, when: str | None = None, kind: str = "fact", key: str = "") -> str | None:
        ts = None
        if when:
            ts = when if "T" in when else f"{when}T12:00:00"
        return self.build([{"content": text, "timestamp": ts, "metadata": {"kind": kind, "key": key}}])[0]

    def delete(self, node_id: str) -> bool:
        self._node_cache = None
        return bool(self._call("delete", id=node_id).get("ok"))

    def nodes(self) -> list[dict]:
        return self._call("nodes")["nodes"]

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        try:
            self._call("ping")
            return True
        except (JevMemError, OSError):
            return False

    def warm_up(self) -> float | None:
        t0 = time.perf_counter()
        try:
            self._call("query", q="hello", top_k=1)
        except JevMemError:
            return None
        return (time.perf_counter() - t0) * 1000

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return list(DOORS)

    def door_cut(self, door: str) -> int | None:
        return self.cut or None

    def _answer(self, query: str) -> dict:
        d = self._call("query", q=query, top_k=self.top_k)
        evidence = str(d.get("evidence") or "")
        if self._traces:
            self._traces[-1]["chars"] = len(evidence)
        semantic, episodic = [], []
        episodes = {x["content"].strip(): x for x in self._nodes_cached() if x.get("kind") == "episode"}
        for line in evidence.splitlines():
            m = _ITEM.match(line)
            if not m:
                continue
            body = m.group(2).strip()
            # as delivered: the date Jev-Mem puts in front of the item stays there
            content = f"[{m.group(1)}] {body}" if m.group(1) else body
            ep = episodes.get(body)
            if ep:
                episodic.append({"created_at": ep.get("timestamp"), "input_summary": body, "output_summary": ""})
            else:
                semantic.append({"source": "jevmem:evidence", "content": content})
        working = []
        for (_, key), _nid in self._live.items():
            m = re.search(re.escape(key) + r":\s*(.+)", evidence)
            if m:
                working.append({"key": key, "value": m.group(1).strip()})
        summary = evidence.strip()
        unknown = []
        if not semantic and not summary.replace("Information not found", "").strip():
            summary = "evidence: none"
            unknown = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", query) if w.lower() not in _STOP][:3]
        return {"summary": summary, "semantic": semantic, "cards": [], "episodic": episodic, "working": working,
                "unknown_terms": unknown, "_raw": d.get("metadata")}

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
        links = self._call("links")["links"]
        contra = sum(v for k, v in links.items() if "CONTRADICT" in k or "OBSOLETE" in k or "SUPERSED" in k)
        return {"links_by_type": links, "superseded_live": 0, "relation_updates": contra}

    def event_date_share(self) -> tuple[int, int]:
        ns = self.nodes()
        return (sum(1 for n in ns if n.get("timestamp")), len(ns))

    # ── episodes and time ─────────────────────────────────────────────────
    def recent_days(self, n: int) -> list[str]:
        ns = self.nodes()
        eps = [x for x in ns if x.get("kind") == "episode"] or ns
        days = {str(x.get("timestamp") or "")[:10] for x in eps}
        return sorted((d for d in days if d), reverse=True)[:n]

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        out = []
        for x in self.nodes():
            if str(x.get("timestamp") or "")[:10] == day:
                out.append({"created_at": x.get("timestamp"), "input_summary": x.get("content"), "output_summary": ""})
        return out[:limit]

    def signed_episodes(self, prefix: str) -> int:
        return sum(1 for x in self.nodes() if str(x.get("content") or "").startswith(prefix))

    # ── live state: build / delete ────────────────────────────────────────
    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool:
        old = self._live.pop((session, key), None)
        if old:
            self.delete(old)
        nid = self.write(f"{key}: {value}", kind="live", key=key)
        if not nid:
            return False
        self._live[(session, key)] = nid
        self._live_at[(session, key)] = time.time()
        return True

    def working_read(self, session: str, key: str):
        nid = self._live.get((session, key))
        if not nid:
            return None
        for x in self.nodes():
            if x["id"] == nid:
                text = str(x.get("content") or "")
                return text.split(":", 1)[1].strip() if ":" in text else text
        return None

    def working_clear(self, session: str) -> None:
        for (s, k), nid in list(self._live.items()):
            if s == session:
                self.delete(nid)
                self._live.pop((s, k), None)

    def working_age_minutes(self, session: str, key: str) -> float | None:
        t = self._live_at.get((session, key))
        return (time.time() - t) / 60 if t else None

    # ── files: none; graph: edges around an entity ────────────────────────
    def file_search(self, query: str, limit: int) -> list[str]:
        return []

    def graph_edges(self, entity: str) -> int:
        return int(self._call("node_links", entity=entity).get("edges") or 0)

    def graph_orphans(self) -> tuple[int, int]:
        return (0, 0)

    def graph_counts(self) -> dict:
        links = self._call("links")["links"]
        return {"nodes": len(self.nodes()), "edges": sum(links.values()), "by_type": links}

    # ── report-only ───────────────────────────────────────────────────────
    def health_report(self) -> tuple[dict, list[str]]:
        info = dict(self._bridge().info)
        info.pop("ok", None)
        return ({"bridge": info, "config": CONFIG},
                ["no entity cards and no files: those sections are SKIP; forget is done by the adapter "
                 "(node, links, vector, index), Jev-Mem has no forget of its own"])

    def measured_doors(self) -> list[str]:
        return ["evidence"]

    def traces(self) -> list[dict]:
        return list(self._traces)

    def probe_doors(self, questions: list[str]) -> None:
        return None

    # ── optional ──────────────────────────────────────────────────────────
    def stored_mentions(self, phrase: str) -> int:
        low = phrase.lower()
        return sum(1 for x in self.nodes() if low in str(x.get("content") or "").lower())

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
