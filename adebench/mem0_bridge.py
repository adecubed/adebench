"""The mem0 side of the adebench adapter: one process, run with mem0's own
Python, that keeps a mem0 `Memory` open and answers JSON lines on stdin.

    <mem0 venv>/python -m adebench.mem0_bridge   (started by adebench.mem0)

It imports nothing from adebench and nothing adebench imports from it: the
harness stays dependency-free, mem0 stays in its own environment. Every
request is one line {"op": ..., ...}; every answer one line {"ok": ..., ...}.
Logging goes to stderr, so stdout carries answers only.

Gemini only: the LLM and the embedder are mem0's own Gemini providers, and
the key is read here from GOOGLE_API_KEY and handed to mem0's config. Every
other cloud key is removed from this process before mem0 is imported, so
nothing can fall back to OpenAI (mem0's default). Telemetry is off
(MEM0_TELEMETRY=False before the import), and everything mem0 writes (its
MEM0_DIR, the history SQLite, the Qdrant collections) lives under MEM0_STORE;
fastembed's BM25 model is cached next to it, in <MEM0_STORE>/../fastembed_cache,
so that emptying the store does not download it again. The key never leaves
this process in clear: it is redacted from every answer and from stderr.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

STORE = Path(os.environ.get("MEM0_STORE", "") or Path(os.environ.get("MEM0_HOME", ".")) / "adebench_store").resolve()
USER = os.environ.get("MEM0_USER_ID", "adebench")
LLM_MODEL = os.environ.get("MEM0_LLM_MODEL", "gemini-3-flash-preview")
EMBED_MODEL = os.environ.get("MEM0_EMBED_MODEL", "models/gemini-embedding-001")
EMBED_DIMS = int(os.environ.get("MEM0_EMBED_DIMS", "768"))
LLM_MAX_TOKENS = int(os.environ.get("MEM0_LLM_MAX_TOKENS", "8192"))   # mem0 default 2000: see adebench.mem0
COLLECTION = "adebench"

_GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY", "")
for _k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "LLM_API_KEY",
           "AZURE_OPENAI_API_KEY", "MISTRAL_API_KEY", "GROQ_API_KEY", "TOGETHER_API_KEY", "DEEPSEEK_API_KEY",
           "XAI_API_KEY", "OPENAI_BASE_URL", "MEM0_API_KEY"):
    os.environ.pop(_k, None)
os.environ.update({
    "MEM0_TELEMETRY": "False",
    "MEM0_DIR": str(STORE / "mem0_dir"),
    "FASTEMBED_CACHE_PATH": str(STORE.parent / "fastembed_cache"),
    "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
})



def _redact(text: str) -> str:
    return text.replace(_GOOGLE_KEY, "[GOOGLE_API_KEY]") if _GOOGLE_KEY else text


class _Redacting:
    """stderr (the bridge log) with the key taken out: a validation error or
    a traceback can echo mem0's config, and the config carries the key."""

    def __init__(self, stream) -> None:
        self.stream = stream

    def write(self, text):
        return self.stream.write(_redact(str(text)))

    def flush(self):
        return self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


sys.stderr = _Redacting(sys.stderr)
_out = sys.stdout
sys.stdout = sys.stderr  # mem0 and qdrant print; keep the answer channel clean

M = None
INFO: dict = {}
LAST: dict = {}
COUNTS = {"llm_calls": 0, "llm_in_tokens": 0, "llm_out_tokens": 0, "llm_thought_tokens": 0,
          "llm_max_tokens_stops": 0, "embed_calls": 0, "embed_texts": 0, "embed_chars": 0}


def _count_calls(m) -> None:
    """Wrap the two google-genai entry points mem0 uses, to count calls and
    tokens for the cost estimate. Nothing is changed on the way through."""
    models = m.llm.client.models
    gen = models.generate_content

    def generate_content(*a, **kw):
        r = gen(*a, **kw)
        COUNTS["llm_calls"] += 1
        u = getattr(r, "usage_metadata", None)
        if u is not None:
            COUNTS["llm_in_tokens"] += int(getattr(u, "prompt_token_count", 0) or 0)
            COUNTS["llm_out_tokens"] += int(getattr(u, "candidates_token_count", 0) or 0)
            COUNTS["llm_thought_tokens"] += int(getattr(u, "thoughts_token_count", 0) or 0)
        for c in getattr(r, "candidates", None) or []:
            LAST["finish_reason"] = str(getattr(c, "finish_reason", ""))
            if "MAX_TOKENS" in LAST["finish_reason"]:
                COUNTS["llm_max_tokens_stops"] += 1
        return r
    models.generate_content = generate_content

    emodels = m.embedding_model.client.models
    emb = emodels.embed_content

    def embed_content(*a, **kw):
        contents = kw.get("contents", a[1] if len(a) > 1 else "")
        texts = contents if isinstance(contents, list) else [contents]
        COUNTS["embed_calls"] += 1
        COUNTS["embed_texts"] += len(texts)
        COUNTS["embed_chars"] += sum(len(str(t)) for t in texts)
        return emb(*a, **kw)
    emodels.embed_content = embed_content


def _config() -> dict:
    llm = {"model": LLM_MODEL, "api_key": _GOOGLE_KEY}
    if LLM_MAX_TOKENS:
        llm["max_tokens"] = LLM_MAX_TOKENS
    return {
        "llm": {"provider": "gemini", "config": llm},
        "embedder": {"provider": "gemini", "config": {"model": EMBED_MODEL, "api_key": _GOOGLE_KEY,
                                                      "embedding_dims": EMBED_DIMS}},
        "vector_store": {"provider": "qdrant", "config": {"collection_name": COLLECTION,
                                                         "path": str(STORE / "qdrant"), "on_disk": True,
                                                         "embedding_model_dims": EMBED_DIMS}},
        "history_db_path": str(STORE / "history.db"),
    }


# ── ops ────────────────────────────────────────────────────────────────────

def op_init(req: dict) -> dict:
    global M, INFO
    if not _GOOGLE_KEY:
        return {"ok": False, "error": "GOOGLE_API_KEY is not set in the environment"}
    t0 = time.perf_counter()
    STORE.mkdir(parents=True, exist_ok=True)
    (STORE / "mem0_dir").mkdir(parents=True, exist_ok=True)
    from mem0 import Memory
    import mem0.memory.telemetry as tel
    import importlib.metadata as md
    M = Memory.from_config(_config())
    _count_calls(M)
    try:
        from mem0.utils.spacy_models import get_nlp_full
        nlp_ok = get_nlp_full() is not None
    except Exception:  # noqa: BLE001
        nlp_ok = False
    INFO = {"ok": True, "mem0_version": md.version("mem0ai"), "telemetry": bool(tel.MEM0_TELEMETRY),
            "llm": f"gemini:{M.config.llm.config.get('model')}",
            "embedder": f"gemini:{EMBED_MODEL} ({EMBED_DIMS} dims)",
            "vector_store": "qdrant, local on disk, <MEM0_STORE>/qdrant",
            "history_db": "sqlite, <MEM0_STORE>/history.db", "user_id": USER,
            "spacy_nlp": nlp_ok, "llm_max_tokens": M.llm.config.max_tokens,
            "init_s": round(time.perf_counter() - t0, 1)}
    return INFO


def _scope(req: dict) -> dict:
    kw = {"user_id": USER}
    if req.get("run_id"):
        kw["run_id"] = req["run_id"]
    return kw


def op_add(req: dict) -> dict:
    """m.add(messages, user_id=..., metadata=..., infer=True): the LLM
    extracts the memories. Returns what mem0 returns (id, memory, event)."""
    t0 = time.perf_counter()
    LAST.clear()
    meta = {k: v for k, v in (req.get("metadata") or {}).items() if v}
    res = M.add(req["messages"], metadata=meta or None, infer=bool(req.get("infer", True)), **_scope(req))
    results = res.get("results", []) if isinstance(res, dict) else (res or [])
    return {"ok": True, "results": [{"id": r.get("id"), "memory": r.get("memory"), "event": r.get("event")}
                                    for r in results], "s": round(time.perf_counter() - t0, 2),
            "llm_finish": LAST.get("finish_reason")}


def _item(r: dict) -> dict:
    return {"id": r.get("id"), "memory": r.get("memory"), "score": r.get("score"),
            "created_at": r.get("created_at"), "run_id": r.get("run_id"), "metadata": r.get("metadata") or {}}


def op_search(req: dict) -> dict:
    t0 = time.perf_counter()
    kw: dict = {"filters": {"user_id": USER}}
    if req.get("top_k"):
        kw["top_k"] = int(req["top_k"])
    res = M.search(req["q"], **kw)
    return {"ok": True, "hits": [_item(r) for r in res.get("results", [])],
            "ms": round((time.perf_counter() - t0) * 1000)}


def _all() -> list[dict]:
    res = M.get_all(filters={"user_id": USER}, top_k=10000)
    return [_item(r) for r in (res.get("results", []) if isinstance(res, dict) else res)]


def op_all(req: dict) -> dict:
    return {"ok": True, "rows": _all()}


def op_get(req: dict) -> dict:
    r = M.get(req["id"])
    return {"ok": True, "row": _item(r) if r else None}


def op_delete(req: dict) -> dict:
    try:
        M.delete(req["id"])
    except ValueError as e:   # "not found": nothing was removed
        return {"ok": False, "error": str(e)}
    return {"ok": True}


def op_health(req: dict) -> dict:
    """The store answers (Qdrant collection, history SQLite) and the embedder
    answers (one embedding): a failure of any of them is an error."""
    c = M.vector_store.client.get_collection(COLLECTION)
    points = M.vector_store.client.count(COLLECTION, exact=True).count
    rows = M.db.connection.execute("SELECT COUNT(*) FROM history").fetchone()[0]
    vec = M.embedding_model.embed("adebench health", "search")
    return {"ok": True, "collection_status": str(getattr(c, "status", "")), "points": points,
            "history_rows": rows, "embedding_dims": len(vec)}


def op_history_counts(req: dict) -> dict:
    ev = dict(M.db.connection.execute("SELECT event, COUNT(*) FROM history GROUP BY event").fetchall())
    return {"ok": True, "events": ev}


def op_history(req: dict) -> dict:
    return {"ok": True, "history": M.history(req["id"])}


def _entities() -> list[dict]:
    rows = M.entity_store.list(filters={"user_id": USER}, top_k=100000)
    rows = rows[0] if isinstance(rows, (list, tuple)) and rows and isinstance(rows[0], list) else rows
    out = []
    for r in rows or []:
        p = getattr(r, "payload", None) or {}
        out.append({"id": str(r.id), "text": p.get("data"), "type": p.get("entity_type"),
                    "linked": [str(x) for x in (p.get("linked_memory_ids") or [])]})
    return out


def op_entities(req: dict) -> dict:
    ents = _entities()
    live = {r["id"] for r in _all()}
    links = sum(len(e["linked"]) for e in ents)
    dangling = sum(1 for e in ents for m in e["linked"] if m not in live)
    orphans = sum(1 for e in ents if any(m not in live for m in e["linked"]))
    by_type: dict = {}
    for e in ents:
        by_type[str(e["type"])] = by_type.get(str(e["type"]), 0) + 1
    out = {"ok": True, "entities": len(ents), "links": links, "dangling_links": dangling,
           "entities_with_dangling_links": orphans, "entities_by_type": by_type, "memories": len(live)}
    if req.get("entity"):
        low = " ".join(req["entity"].lower().replace("_", " ").split())
        out["entity_links"] = sum(len(e["linked"]) for e in ents
                                  if " ".join(str(e["text"] or "").lower().split()) == low)
    return out


def op_messages(req: dict) -> dict:
    """What mem0 keeps verbatim: the messages it saves per session scope
    (the last 10 of each scope; older ones are evicted by mem0 itself)."""
    rows = M.db.connection.execute(
        "SELECT session_scope, role, content, created_at FROM messages ORDER BY created_at").fetchall()
    return {"ok": True, "messages": [{"scope": r[0], "role": r[1], "content": r[2], "created_at": r[3]}
                                     for r in rows]}


def op_stats(req: dict) -> dict:
    return {"ok": True, **COUNTS}


OPS = {"init": op_init, "add": op_add, "search": op_search, "all": op_all, "get": op_get, "delete": op_delete,
       "health": op_health, "history_counts": op_history_counts, "history": op_history,
       "entities": op_entities, "stats": op_stats, "messages": op_messages, "ping": lambda r: {"ok": True}}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            op = OPS[req["op"]]
            if M is None and req["op"] not in ("init", "ping"):
                ans = {"ok": False, "error": "not initialised"}
            else:
                ans = op(req)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            ans = {"ok": False, "error": f"{type(e).__name__}: {e}"[:500]}
        _out.write(_redact(json.dumps(ans, default=str)) + "\n")
        _out.flush()


if __name__ == "__main__":
    main()
