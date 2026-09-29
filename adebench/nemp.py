"""Adapter for Nemp (github.com/SukinShetty/Nemp-memory): a Claude Code plugin
whose memory is a JSON file in the project (.nemp/memories.json) and whose
engine is the model itself. Nemp has no code: every command is a markdown
file of instructions that Claude Code follows with its own tools (Bash,
Read, Write, Edit).

So the only honest door is the harness. Every operation here is one
`claude -p "/nemp:<command> ..."` in a scratch project, with Nemp loaded for
that call only (--plugin-dir), no user settings, no MCP server, and a fixed
model. The adapter reads the stream-json transcript of the call: what the
model received from its tools during the turn is the `context` door, what
the command printed is the `shown` door. The store file is read directly
only for report measures (dates, counts, live-state values).

    git clone https://github.com/SukinShetty/Nemp-memory
    NEMP_PLUGIN=.../Nemp-memory NEMP_PROJECT=/tmp/nemp-project python examples/nemp_import.py
    python -m adebench --adapter adebench.nemp:NempAdapter --cases examples/synthetic_data/cases

    NEMP_PLUGIN    the Nemp checkout (loaded with --plugin-dir)
    NEMP_PROJECT   the scratch project (a git repository, so Nemp uses project storage)
    NEMP_MODEL     the model that runs the commands (default sonnet)
    CLAUDE_BIN     the Claude Code CLI (default claude)

Doors:
  context  everything the model received from its tools while running
           /nemp:context <question>: Nemp has it cat and Read the whole
           memories.json, so this is the whole store, every time
  shown    what /nemp:context printed: the memories it matched

What maps and what does not (SKIP is honest, not a zero):
  cards          none; aliases, corrections: none (written as memories)
  fact updates   a key is the only id: the same key overwrites, a new key adds.
                 write_fact(text) has no id, so its key is a fresh one
                 (fact-<hash>), as for every memory in the probe
  time           a memory carries its write time (created/updated), no event
                 date: what the corpus dates is lost unless the text says it
  live state     a key is saved with /nemp:save and read back from the store
  files, graph   none: SKIP
Every call is a model turn (20-30 s), and the run's cost is in the report.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

from adebench.ade import competing_payload
from adebench.config import CFG

PLUGIN = os.environ.get("NEMP_PLUGIN", "")
PROJECT = os.environ.get("NEMP_PROJECT", "")
MODEL = os.environ.get("NEMP_MODEL", "sonnet")
CLAUDE = os.environ.get("CLAUDE_BIN", "claude")
DOORS = ("context", "shown")
_TOOLS = "Bash,Read,Write,Edit,Glob,Grep"


class NempError(RuntimeError):
    pass


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "memory"


class NempAdapter:
    def __init__(self) -> None:
        if not PLUGIN or not PROJECT:
            raise NempError("set NEMP_PLUGIN (the Nemp checkout) and NEMP_PROJECT (a scratch git repository)")
        self.project = Path(PROJECT)
        self.cut = int(os.environ.get("ADEBENCH_NEMP_CUT", "0"))
        self._traces: list[dict] = []
        self._cache: dict[str, dict] = {}
        self._live: dict[tuple[str, str], str] = {}
        self.cost_usd = 0.0
        self.calls = 0

    # ── one model turn ────────────────────────────────────────────────────
    def run(self, prompt: str, timeout: float = 600) -> dict:
        cmd = [CLAUDE, "-p", prompt, "--model", MODEL, "--plugin-dir", PLUGIN,
               "--setting-sources", "project", "--strict-mcp-config", "--tools", _TOOLS,
               "--allowedTools", " ".join(_TOOLS.split(",")), "--permission-mode", "acceptEdits",
               "--no-session-persistence", "--output-format", "stream-json", "--verbose"]
        t0 = time.perf_counter()
        p = subprocess.run(cmd, cwd=self.project, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        ms = (time.perf_counter() - t0) * 1000
        received, shown, cost, ok = [], "", 0.0, False
        for line in p.stdout.splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") == "user" and isinstance(e.get("message", {}).get("content"), list):
                for c in e["message"]["content"]:
                    if c.get("type") == "tool_result":
                        cont = c.get("content")
                        if isinstance(cont, list):
                            cont = "\n".join(x.get("text", "") for x in cont if isinstance(x, dict))
                        received.append(str(cont or ""))
            elif e.get("type") == "result":
                shown = str(e.get("result") or "")
                cost = float(e.get("total_cost_usd") or 0)
                ok = not e.get("is_error")
        self.calls += 1
        self.cost_usd += cost
        self._traces.append({"door": prompt.split()[0], "ms": ms, "chars": sum(len(r) for r in received),
                             "http": 200 if ok else 500})
        if not ok:
            raise NempError(f"{prompt.split()[0]}: {(shown or p.stderr)[:200]}")
        return {"received": received, "shown": shown, "ms": ms}

    # ── the store, for measures only ──────────────────────────────────────
    def memories(self) -> list[dict]:
        f = self.project / ".nemp" / "memories.json"
        if not f.exists():
            return []
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            return []
        items = d.get("memories") if isinstance(d, dict) and "memories" in d else d
        if isinstance(items, dict):
            items = [{"key": k, "value": v} if not isinstance(v, dict) else {"key": k, **v} for k, v in items.items()]
        return [m for m in (items or []) if isinstance(m, dict)]

    # ── writing ───────────────────────────────────────────────────────────
    def save(self, key: str, value: str) -> str | None:
        self._cache.clear()
        self.run(f"/nemp:save {key} {value}")
        return key if any(m.get("key") == key for m in self.memories()) else None

    def forget(self, key: str) -> bool:
        self._cache.clear()
        self.run(f"/nemp:forget {key} --force")
        return not any(m.get("key") == key for m in self.memories())

    # ── liveness ──────────────────────────────────────────────────────────
    def health(self) -> bool:
        return bool(PLUGIN) and (Path(PLUGIN) / ".claude-plugin" / "plugin.json").exists() and self.project.exists()

    def warm_up(self) -> float | None:
        return None

    # ── doors ─────────────────────────────────────────────────────────────
    def doors(self) -> list[str]:
        return list(DOORS)

    def door_cut(self, door: str) -> int | None:
        return self.cut or None

    def _answer(self, query: str) -> dict:
        if query in self._cache:
            return self._cache[query]
        r = self.run(f"/nemp:context {query}")
        context = "\n".join(r["received"])
        shown = r["shown"]
        keys = {m.get("key") for m in self.memories()}
        matched = [k for k in keys if k and re.search(r"(?<![\w-])" + re.escape(k) + r"(?![\w-])", shown)]
        by_key = {m.get("key"): m for m in self.memories()}
        semantic = [{"source": "nemp:shown", "key": k, "content": str(by_key[k].get("value") or "")} for k in matched]
        working = [{"key": k, "value": str(by_key[k].get("value") or "")}
                   for (_, k) in self._live if k in matched]
        out = {"summary": shown, "context": context, "semantic": semantic, "cards": [], "episodic": [],
               "working": working, "unknown_terms": [], "_ms": r["ms"]}
        self._cache[query] = out
        return out

    def door_text(self, query: str, door: str) -> tuple[str, dict]:
        r = self._answer(query)
        body = r["shown"] if door == "shown" else r["context"] + "\n" + r["summary"]
        text = competing_payload(CFG.pressure) + body
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
        ms = self.memories()
        return {"memories": len(ms), "updated_in_place": sum(1 for m in ms if (m.get("vitality") or {}).get("update_count")),
                "superseded_live": 0, "relation_updates": sum(1 for m in ms if (m.get("links") or {}).get("superseded_by"))}

    def event_date_share(self) -> tuple[int, int]:
        ms = self.memories()
        return (0, len(ms))

    # ── episodes and time: write time only ────────────────────────────────
    def recent_days(self, n: int) -> list[str]:
        days = {str(m.get("created") or "")[:10] for m in self.memories() if str(m.get("key", "")).startswith("episode")}
        return sorted((d for d in days if d), reverse=True)[:n]

    def episodes_of_day(self, day: str, limit: int) -> list[dict]:
        return [{"created_at": m.get("created"), "input_summary": str(m.get("value") or ""), "output_summary": ""}
                for m in self.memories()
                if str(m.get("key", "")).startswith("episode") and str(m.get("created") or "")[:10] == day][:limit]

    def signed_episodes(self, prefix: str) -> int:
        return sum(1 for m in self.memories() if str(m.get("value") or "").startswith(prefix))

    # ── live state: /nemp:save on a key ───────────────────────────────────
    def working_write(self, session: str, key: str, value: str, ttl_hours: int) -> bool:
        k = f"live-{slug(key)}"
        ok = self.save(k, f"{key}: {value}") is not None
        if ok:
            self._live[(session, k)] = key
        return ok

    def working_read(self, session: str, key: str):
        k = f"live-{slug(key)}"
        for m in self.memories():
            if m.get("key") == k:
                v = str(m.get("value") or "")
                return v.split(":", 1)[1].strip() if ":" in v else v
        return None

    def working_clear(self, session: str) -> None:
        for (s, k) in list(self._live):
            if s == session:
                self.forget(k)
                self._live.pop((s, k), None)

    def working_age_minutes(self, session: str, key: str) -> float | None:
        return None

    # ── files and graph: none ─────────────────────────────────────────────
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
        f = self.project / ".nemp" / "memories.json"
        return ({"model": MODEL, "calls": self.calls, "cost_usd": round(self.cost_usd, 2),
                 "memories": len(self.memories()), "store_bytes": f.stat().st_size if f.exists() else 0},
                ["every operation is a model turn: the result depends on the model that follows Nemp's instructions",
                 "the context door is the whole store (cat + Read of memories.json on every lookup)"])

    def measured_doors(self) -> list[str]:
        return ["context", "shown"]

    def traces(self) -> list[dict]:
        return list(self._traces)

    def probe_doors(self, questions: list[str]) -> None:
        return None

    # ── optional ──────────────────────────────────────────────────────────
    def stored_mentions(self, phrase: str) -> int:
        low = phrase.lower()
        return sum(1 for m in self.memories() if low in str(m.get("value") or "").lower())

    def write_fact(self, text: str):
        return self.save("fact-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8], text)

    def forget_memory(self, memory_id: str) -> bool:
        return self.forget(memory_id)

    def import_memory(self, text: str, written_at: str):
        return self.save("imported-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:8], text)

    def ingest_exchange(self, question: str, answer: str):
        return self.save("exchange-" + hashlib.sha1((question + answer).encode("utf-8")).hexdigest()[:8],
                         f"User: {question} Assistant: {answer}")
