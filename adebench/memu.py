"""Adapter for memU (github.com/NevaMind-AI/memU, Apache-2.0): "personal
memory, stored as Wiki". Memory is a set of markdown recall files (name,
description, content); every content line is a segment with its own
embedding, and retrieval ranks segments by vector similarity and rolls them up
to their files. Self-hosted only here: SQLite store, no memu.so account.

memU calls no LLM itself. Writing goes through `memorize`: memU prepares job
files from 1-10 sessions (user/assistant messages), an EXTERNAL agent carries
them out (reads the session, reads the existing wiki pages, creates, patches
or leaves them), and memU commits what changed, embedding the new lines.
Reading is `progressive_retrieve` (`memu retrieve`): one embedding of the
query, top-5 segments, their files, resources. No LLM on the read side.

adebench does not import memU: this adapter starts `adebench/memu_bridge.py`
with memU's own Python and talks to it in JSON lines (the cognee pattern).
The bridge was chosen over the `memu` CLI because the CLI fixes the memorize
workspace at ~/.memu/developer (the user's home) and leaves the executor to
the caller anyway; the library takes the workspace as a parameter and the
bridge keeps one store and one embedding client open for the whole run.

Models (measured configuration):
  executor LLM  gemini-3-flash-preview, Google's OpenAI-compatible endpoint
                (https://generativelanguage.googleapis.com/v1beta/openai/
                chat/completions, function calling, default thinking), run
                by the bridge as memU's external agent: it receives memU's own
                executor prompt and job files verbatim, with five file tools
                confined to the workspace (read_file, list_dir, write_file,
                append_line, run_command for memU's verify command only)
                instead of a shell. The paths it sees are relative to the
                store (`workspace/...`): no absolute path, no user name, goes
                to Google. The score is memU PLUS this executor; the report's
                health section carries the setup (measures.executor)
  embeddings    gemini-embedding-001 (3072 dims) through memU's own "openai"
                provider (the OpenAI SDK client) with base_url set to the same
                Google endpoint: MEMU_EMBED_PROVIDER=openai + MEMU_BASE_URL
  key           GOOGLE_API_KEY, read from the environment inside the bridge;
                every other provider key is removed from the bridge's
                environment. Telemetry, template and docs refresh are off.
  memU build    source main (memu-cli 0.11.0b3 from git): the PyPI wheels
                (0.10.0, 0.11.0b3) do not ship `memu memorize`

    uv venv --python 3.11 .venv && uv pip install --python .venv/Scripts/python.exe <memU checkout>
    MEMU_HOME=... MEMU_PYTHON=.../.venv/Scripts/python.exe python examples/memu_import.py
    ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.memu:MemuAdapter \\
        --cases sets/quick/cases --no-sandbox-test --write-back

    MEMU_HOME       the directory of the memU install (its venv)
    MEMU_PYTHON     the Python of memU's environment
    MEMU_STORE      where the SQLite store, the memorize workspace and a
                    private HOME live (default <MEMU_HOME>/adebench_store;
                    never the user's home)
    GOOGLE_API_KEY  the Gemini key (executor and embeddings)
    MEMU_EXECUTOR_MODEL  the executor model (default gemini-3-flash-preview)
    MEMU_EMBED_MODEL_ADEBENCH  the embedding model (default gemini-embedding-001;
                    not memU's own MEMU_EMBED_MODEL, which the bridge clears)
    MEMU_EXECUTOR_MAX_STEPS  model turns the executor may take for one prepared
                    run (up to 10 sessions) before it is abandoned (default 200)
    ADEBENCH_MEMU_CUT    a character cut on the door (default none)

Doors:
  retrieve  literally what `memu retrieve` prints for the question: the JSON of
            progressive_retrieve (indent 2): the top-5 segments with their
            score and timestamps, the files they roll up to with description
            and full content, the resources. No cut.
  hook      literally what a host adapter's `memu-<host> retrieve` prints:
            memU's own _shape_for_agent of the same result, segments with
            their source_file, files with the `path` of their mirror
            (~/.memu/memory/<name>.md) instead of the content. Measured on the
            side (probe_doors); run it with --door hook.

What maps and what does not (SKIP is honest, not a zero):
  cards          none: a recall file is a wiki page the executor names, not an
                 entity card. Corrections, aliases: none (an alias goes in as
                 a sentence)
  fact updates   memU has no supersession of its own; what replaces what is the
                 executor's patch of a page. write_fact = one memorize run of a
                 one-message session; the harness probe decides
  forget         memU has no per-memory delete (commit cannot delete a file).
                 forget_memory undoes one memorize run: the files it changed are
                 committed back to what they held before, a file it created is
                 emptied (its segments go, the empty row stays). The bridge
                 keeps what each run committed and REFUSES the revert (False,
                 nothing written) when a file changed after the run, instead
                 of restoring a stale snapshot over a later write
  time           memorize input accepts no timestamp (unknown fields are
                 rejected), so no event date reaches memU. The adapter adds no
                 date: the storage timestamps in memU's JSON are write times,
                 not a memory's age. import_memory carries no original date.
                 No episodes: the day filter and signed episodes are SKIP
  live state     a key is one recall file "adebench-live-<session>-<key>" with
                 "<key>: <value>", written straight through commit_results (what
                 `memu commit` does, no LLM), overwritten in place, emptied on
                 clear; seen at the door when a hit comes from that file
  files          not mapped (memU resources are files an agent touched): SKIP
  graph          none: SKIP
  declared bytes memU has no MCP server: not measured
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from adebench.ade import competing_payload
from adebench.config import CFG

HOME = os.environ.get("MEMU_HOME", "")
PY = os.environ.get("MEMU_PYTHON", "")
STORE = os.environ.get("MEMU_STORE", "") or (str(Path(HOME) / "adebench_store") if HOME else "")
DOORS = ("retrieve", "hook")
LIVE_PREFIX = "adebench-live-"
_STOP = {"what", "which", "who", "when", "where", "does", "is", "the", "how", "many", "much", "about",
         "with", "for", "and", "that", "this", "are", "was", "were", "have", "has", "did"}
# keys that must not reach memU's process: only GOOGLE_API_KEY is used
_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "JINA_API_KEY", "VOYAGE_API_KEY", "ARK_API_KEY",
         "OPENROUTER_API_KEY", "MEMU_API_KEY", "MEMU_CLOUD_API_KEY", "GEMINI_API_KEY", "LLM_API_KEY",
         "EMBEDDING_API_KEY", "AZURE_OPENAI_API_KEY", "MISTRAL_API_KEY", "GROQ_API_KEY")


class MemuError(RuntimeError):
    pass


class _Bridge:
    def __init__(self, fresh: bool = False) -> None:
        if not HOME or not PY:
            raise MemuError("set MEMU_HOME (the memU install) and MEMU_PYTHON (its Python)")
        env = {k: v for k, v in os.environ.items() if k not in _KEYS}
        env.update(MEMU_HOME=HOME, MEMU_STORE=STORE, PYTHONIOENCODING="utf-8",
                   PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        Path(STORE).mkdir(parents=True, exist_ok=True)
        self.log = open(Path(STORE) / "memu_bridge.log", "a", encoding="utf-8")
        self.p = subprocess.Popen([PY, "-m", "adebench.memu_bridge"], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=self.log, env=env,
                                  text=True, encoding="utf-8", bufsize=1)
        self.lock = threading.Lock()
        self.info = self.call("init", fresh=fresh)

    def call(self, op: str, **kw) -> dict:
        with self.lock:
            if self.p.poll() is not None:
                raise MemuError(f"bridge exited with code {self.p.returncode}")
            self.p.stdin.write(json.dumps({"op": op, **kw}) + "\n")
            self.p.stdin.flush()
            line = self.p.stdout.readline()
        if not line:
            raise MemuError(f"{op}: no answer from the bridge")
        d = json.loads(line)
        if not d.get("ok"):
            raise MemuError(f"{op}: {d.get('error')}")
        return d

    def close(self) -> None:
        try:
            self.p.stdin.close()
            self.p.wait(timeout=30)
        except Exception:  # noqa: BLE001
            self.p.kill()


def printed(payload: dict) -> str:
    """What memU's CLIs print for a retrieve: `memu retrieve` and the host
    adapters' `retrieve` both write json.dumps(result, indent=2,
    ensure_ascii=False, default=str) to stdout."""
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def door_payload(d: dict, door: str) -> dict:
    """The bridge's answer -> the payload that door prints."""
    return d["shaped"] if door == "hook" else d["result"]


class MemuAdapter:
    def __init__(self, fresh: bool = False) -> None:
        self.fresh = fresh
        self.cut = int(os.environ.get("ADEBENCH_MEMU_CUT", "0"))
        self._b: _Bridge | None = None
        self._traces: list[dict] = []
        self._memorize_log: list[dict] = []

    def _bridge(self) -> _Bridge:
        if self._b is None:
            self._b = _Bridge(fresh=self.fresh)
        return self._b

    def _call(self, op: str, **kw) -> dict:
        return self._bridge().call(op, **kw)

    # ── writing ───────────────────────────────────────────────────────────
    def memorize(self, sessions: list[list[dict]]) -> list[dict]:
        """sessions: [[{role, content}, ...], ...] through memU's memorize
        (prepare, executor, commit), 10 sessions per run. Returns the runs."""
        runs = self._call("memorize", sessions=sessions)["runs"]
        self._memorize_log.extend({k: r[k] for k in ("sessions", "jobs", "s", "changed")} for r in runs)
        return runs

    def _write_session(self, messages: list[dict]) -> str:
        return self.memorize([messages])[0]["id"]

    def files(self) -> list[dict]:
        return self._call("files")["files"]

    def _live_name(self, session: str, key: str) -> str:
        return f"{LIVE_PREFIX}{session}-{key}".replace(" ", "-")

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        """The store lists its files AND the embedding provider returns a
        vector: a retrieve needs both."""
        try:
            h = self._call("health")
        except (MemuError, OSError):
            return False
        return int(h.get("embed_dims") or 0) > 0

    def warm_up(self) -> float | None:
        t0 = time.perf_counter()
        try:
            self._call("retrieve", q="hello", door="retrieve")
        except MemuError:
            return None
        return (time.perf_counter() - t0) * 1000

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return list(DOORS)

    def door_cut(self, door: str) -> int | None:
        return self.cut or None

    def _retrieve(self, query: str, door: str) -> dict:
        t0 = time.perf_counter()
        failed, chars = False, 0
        try:
            d = self._call("retrieve", q=query, door=door)
            chars = len(printed(door_payload(d, door)))
            return d
        except MemuError:
            failed = True
            raise
        finally:
            self._traces.append({"door": door, "ms": (time.perf_counter() - t0) * 1000,
                                 "chars": chars, "http": 500 if failed else 200})

    def _answer(self, query: str, door: str = "retrieve") -> dict:
        t0 = time.perf_counter()
        d = self._retrieve(query, door)
        result = d["result"]
        text = printed(door_payload(d, door))
        live_ids = {f.get("id") for f in result.get("files", []) if str(f.get("name", "")).startswith(LIVE_PREFIX)}
        semantic, working = [], []
        for seg in result.get("segments", []):
            seg_text = str(seg.get("text") or "")
            if seg.get("recall_file_id") in live_ids and ": " in seg_text:
                key, _, value = seg_text.partition(": ")
                working.append({"key": key, "value": value.strip()})
            else:
                # every segment is a nearest neighbour by meaning: memU has no
                # keyword leg and no relevance floor, it returns top_k always.
                # The line as memU stores it: no date is added (memU keeps none)
                semantic.append({"source": "semantic_vec:memu_segment", "content": seg_text,
                                 "key": seg.get("recall_file_id"), "_score": seg.get("score")})
        unknown = []
        if not result.get("segments"):
            unknown = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", query) if w.lower() not in _STOP][:3]
        return {"summary": text, "semantic": semantic, "cards": [], "episodic": [], "working": working,
                "unknown_terms": unknown, "_ms": (time.perf_counter() - t0) * 1000,
                "_raw": [{"file": f"{f.get('track')}/{f.get('name')}", "score": f.get("score")}
                         for f in result.get("files", [])]}

    def door_text(self, query: str, door: str) -> tuple[str, dict]:
        r = self._answer(query, door if door in DOORS else "retrieve")
        text = competing_payload(CFG.pressure) + r["summary"]
        return (text[:self.cut] if self.cut else text), r

    def ask(self, query: str) -> dict:
        return self._answer(query, "retrieve")

    # ── cards, corrections, aliases: none ─────────────────────────────────
    def cards(self) -> list[dict]:
        return []

    def corrections(self) -> list[dict]:
        return []

    def aliases(self) -> list[dict]:
        return []

    # ── facts and their lifecycle ─────────────────────────────────────────
    def update_trace(self) -> dict:
        fs = [f for f in self.files() if not str(f.get("name", "")).startswith(LIVE_PREFIX)]
        return {"superseded_live": 0, "relation_updates": 0,
                "recall_files": sum(1 for f in fs if (f.get("content") or "").strip()),
                "empty_recall_files": sum(1 for f in fs if not (f.get("content") or "").strip()),
                "segments": self._call("segments")["segments"]}

    def event_date_share(self) -> tuple[int, int]:
        # no event date field anywhere in memU: every page counts, none is dated
        fs = [f for f in self.files() if (f.get("content") or "").strip()
              and not str(f.get("name", "")).startswith(LIVE_PREFIX)]
        return (0, len(fs))

    # ── episodes and time: memU keeps no episodes ─────────────────────────
    def recent_days(self, n: int) -> list[str]:
        return []

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        return []

    def signed_episodes(self, prefix: str) -> int:
        return 0

    # ── live state: one recall file per key, straight through commit ──────
    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool:
        name = self._live_name(session, key)
        d = self._call("put", name=name, description=f"live state {key}", content=f"{key}: {value}")
        return name in d.get("files", [])

    def _live_file(self, session: str, key: str) -> dict | None:
        name = self._live_name(session, key)
        return next((f for f in self.files() if f.get("name") == name), None)

    def working_read(self, session: str, key: str):
        f = self._live_file(session, key)
        text = str((f or {}).get("content") or "").strip()
        if not text:
            return None
        return text.split(": ", 1)[1].strip() if ": " in text else text

    def working_clear(self, session: str) -> None:
        prefix = f"{LIVE_PREFIX}{session}-"
        for f in self.files():
            if str(f.get("name", "")).startswith(prefix) and (f.get("content") or "").strip():
                self._call("put", name=f["name"], description=f.get("description") or "", content="")

    def working_age_minutes(self, session: str, key: str) -> float | None:
        f = self._live_file(session, key)
        if not f or not (f.get("content") or "").strip():
            return None
        try:
            t = datetime.fromisoformat(str(f["updated_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            return None
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 60

    # ── files, graph: none ────────────────────────────────────────────────
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
        info = dict(self._bridge().info)
        info.pop("ok", None)
        measures: dict = {"bridge": info, "memorize_runs": list(self._memorize_log)}
        warnings = ["the score is memU PLUS its external executor: memU calls no LLM, memorize hands its "
                    "job files to an agent; here gemini-3-flash-preview with file tools and no shell "
                    "(measures.executor)",
                    "no entity cards, no episodes, no graph, no files: those sections are SKIP; memU's "
                    "retrieve is a vector search over page lines with no relevance floor: it always "
                    "returns its top 5",
                    "no event dates: memorize input accepts no timestamp; memU's timestamps are write times"]
        for op, key in (("executor", "executor"), ("usage", "usage")):
            try:
                measures[key] = self._call(op)[key]
            except MemuError as e:
                warnings.append(str(e)[:160])
        try:
            measures["health"] = self._call("health")
        except MemuError as e:
            warnings.append(f"memU health: {str(e)[:160]}")
        return measures, warnings

    def measured_doors(self) -> list[str]:
        return list(DOORS)

    def traces(self) -> list[dict]:
        return list(self._traces)

    def probe_doors(self, questions: list[str]) -> None:
        for q in questions:
            try:
                self._answer(q, "hook")
            except MemuError:
                pass

    # ── optional ──────────────────────────────────────────────────────────
    def stored_mentions(self, phrase: str) -> int:
        low = phrase.lower()
        return sum(1 for f in self.files() if low in str(f.get("content") or "").lower())

    def write_fact(self, text: str):
        return self._write_session([{"role": "user", "content": text}])

    def forget_memory(self, memory_id: str) -> bool:
        try:
            return bool(self._call("forget", id=memory_id).get("ok"))
        except MemuError:
            return False

    def import_memory(self, text: str, written_at: str):
        # written_at has nowhere to go: memorize input rejects timestamps
        return self._write_session([{"role": "user", "content": text}])

    def ingest_exchange(self, question: str, answer: str):
        return self._write_session([{"role": "user", "content": question},
                                    {"role": "assistant", "content": answer}])

    def settle(self) -> None:
        """Nothing pending: memorize commits (and embeds) before it returns."""
        return None

    def declared_bytes(self) -> int | None:
        return None
