"""The cognee side of the adebench adapter: one process, run with cognee's own
Python, that keeps cognee (and its local models) loaded and answers JSON lines
on stdin.

    <cognee venv>/python -m adebench.cognee_bridge   (started by adebench.cognee)

It imports nothing from adebench and nothing adebench imports from it: the
harness stays dependency-free, cognee stays in its own environment. Every
request is one line {"op": ..., ...}; every answer one line {"ok": ..., ...}.
Logging goes to stderr, so stdout carries answers only.

Two modes (COGNEE_LLM). gemini (default): cognee's documented Gemini setup,
the key read from GOOGLE_API_KEY in this process and moved to LLM_API_KEY /
EMBEDDING_API_KEY. gliner_demo: the no-key mode (GLiNER demo extraction,
fastembed embeddings, CHUNKS at recall). In both, every other cloud key is
removed before cognee is imported and telemetry is off. All of cognee's
directories (data, system databases, cache, logs, repos) live under
COGNEE_STORE (default COGNEE_HOME/adebench_store_<mode>), never the home
default. Every recall runs in a fresh session_id: cognee's session memory
(on by default) never feeds the benchmark's earlier questions back in.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import traceback
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

HOME = Path(os.environ.get("COGNEE_HOME", ".")).resolve()
MODE = os.environ.get("COGNEE_LLM", "gemini").lower()
if MODE in ("gliner", "local"):
    MODE = "gliner_demo"
STORE = Path(os.environ.get("COGNEE_STORE", "") or HOME / f"adebench_store_{MODE}").resolve()
DATASET = os.environ.get("COGNEE_DATASET", "adebench")
GEMINI_MODEL = os.environ.get("COGNEE_LLM_MODEL", "gemini/gemini-3-flash-preview")
GEMINI_EMBEDDING = os.environ.get("COGNEE_EMBEDDING_MODEL", "gemini/gemini-embedding-001")

# The Google key is read here, in process, and handed to cognee as its LLM and
# embedding key (Gemini mode only). Every other cloud key and model setting is
# removed, so nothing else can be reached.
_google = os.environ.get("GOOGLE_API_KEY", "")
for _k in ("LLM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
           "EMBEDDING_API_KEY", "AZURE_OPENAI_API_KEY", "MISTRAL_API_KEY", "GROQ_API_KEY",
           "LLM_PROVIDER", "LLM_MODEL", "LLM_ENDPOINT", "EMBEDDING_PROVIDER", "EMBEDDING_MODEL",
           "EMBEDDING_ENDPOINT", "EMBEDDING_DIMENSIONS", "GRAPH_EXTRACTOR"):
    os.environ.pop(_k, None)
if MODE == "gemini":
    if not _google:
        raise SystemExit("COGNEE_LLM=gemini needs GOOGLE_API_KEY in the environment")
    # cognee's documented Gemini setup (docs.cognee.ai, LLM and embedding providers)
    os.environ.update({"LLM_PROVIDER": "gemini", "LLM_MODEL": GEMINI_MODEL, "LLM_API_KEY": _google,
                       "EMBEDDING_PROVIDER": "gemini", "EMBEDDING_MODEL": GEMINI_EMBEDDING,
                       "EMBEDDING_DIMENSIONS": "768", "EMBEDDING_API_KEY": _google,
                       "GRAPH_EXTRACTOR": "llm"})
elif MODE == "gliner_demo":
    os.environ["GRAPH_EXTRACTOR"] = "gliner_demo"   # zero cost: no cloud model reachable
else:
    raise SystemExit(f"COGNEE_LLM={MODE}: expected gemini or gliner_demo")
del _google
os.environ.update({
    "DATA_ROOT_DIRECTORY": str(STORE / "data"),
    "SYSTEM_ROOT_DIRECTORY": str(STORE / "system"),
    "CACHE_ROOT_DIRECTORY": str(STORE / "cache"),
    "COGNEE_LOGS_DIR": str(STORE / "logs"),
    "COGNEE_REPOS_DIR": str(STORE / "repos"),
    "TELEMETRY_DISABLED": "1",
    "GLINER_AUTO_INSTALL": "false",   # installed with cognee[gliner]; never pip at run time
    "HF_HUB_DISABLE_SYMLINKS_WARNING": "1",
})
STORE.mkdir(parents=True, exist_ok=True)
os.chdir(STORE)   # cognee reads a .env from the cwd: this one has none

_out = sys.stdout
sys.stdout = sys.stderr  # cognee logs; keep the answer channel clean

LOOP = asyncio.new_event_loop()
cognee = None
_texts: dict[str, str] = {}


def run(coro):
    return LOOP.run_until_complete(coro)


async def _dataset():
    for d in await cognee.datasets.list_datasets():
        if d.name == DATASET:
            return d
    return None


def _read_location(loc: str) -> str:
    if not loc:
        return ""
    p = urlparse(loc)
    path = unquote(p.path) if p.scheme == "file" else loc
    if p.scheme == "file" and len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]   # file:///C:/... on Windows
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _meta(v) -> dict:
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip().startswith("{"):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return {}
    return {}


# ── ops ────────────────────────────────────────────────────────────────────

USAGE: dict = {}


def _meter() -> None:
    """Count every litellm call cognee makes (LLM and embeddings), with tokens."""
    import litellm
    from litellm.integrations.custom_logger import CustomLogger

    class _Meter(CustomLogger):
        def _add(self, kwargs, response_obj):
            model = str(kwargs.get("model") or "?")
            kind = str(kwargs.get("call_type") or "?")
            u = getattr(response_obj, "usage", None)
            get = (lambda k: (u.get(k) if isinstance(u, dict) else getattr(u, k, 0)) or 0)
            row = USAGE.setdefault(f"{kind}:{model}", {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0})
            row["calls"] += 1
            row["prompt_tokens"] += int(get("prompt_tokens"))
            row["completion_tokens"] += int(get("completion_tokens"))

        def log_success_event(self, kwargs, response_obj, start_time, end_time):
            self._add(kwargs, response_obj)

        async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
            self._add(kwargs, response_obj)

    litellm.callbacks.append(_Meter())


_STARTED = time.strftime("%Y-%m-%dT%H:%M:%S")


def _save_usage() -> None:
    """The calls and tokens this bridge process spent, for the cost estimate:
    COGNEE_HOME/cognee_usage/<start>_<pid>.json, rewritten after every request
    (the harness may end without closing the bridge)."""
    if USAGE:
        d = HOME / "cognee_usage"
        d.mkdir(exist_ok=True)
        (d / f"{_STARTED.replace(':', '')}_{os.getpid()}.json").write_text(
            json.dumps({"started": _STARTED, "store": STORE.name, "usage": USAGE}), encoding="utf-8")


def op_usage(req: dict) -> dict:
    return {"ok": True, "usage": USAGE}


def op_init(req: dict) -> dict:
    global cognee
    t0 = time.perf_counter()
    import cognee as _c
    cognee = _c
    if MODE == "gemini":
        _meter()
    cognee.config.data_root_directory(str(STORE / "data"))
    cognee.config.system_root_directory(str(STORE / "system"))
    if req.get("fresh"):
        run(cognee.prune.prune_data())
        run(cognee.prune.prune_system(metadata=True))
        _texts.clear()
    from cognee.modules.cognify.config import get_cognify_config, resolve_extractor
    from cognee.infrastructure.databases.vector.embeddings.config import (
        get_embedding_config, resolve_embedding_defaults)
    from cognee.infrastructure.llm.config import get_llm_config
    # what the engine really runs with (keyless: the local fastembed model),
    # not the config's nominal default
    provider, model, dims = resolve_embedding_defaults(get_embedding_config(), get_llm_config())
    llm = get_llm_config()
    info = {"ok": True, "cognee_version": getattr(cognee, "__version__", None), "mode": MODE,
            "llm": f"{llm.llm_provider}:{llm.llm_model}" if MODE == "gemini" else None,
            "store": STORE.name,
            "dataset": DATASET, "extractor": resolve_extractor(None, get_cognify_config()),
            "embedding": f"{provider}:{model} ({dims} dims)",
            "init_s": round(time.perf_counter() - t0, 1)}
    try:
        from cognee.infrastructure.databases.vector.config import get_vectordb_config
        from cognee.infrastructure.databases.graph.config import get_graph_config
        info["vector_db"] = get_vectordb_config().vector_db_provider
        info["graph_db"] = get_graph_config().graph_database_provider
    except Exception:  # noqa: BLE001
        pass
    return info


def op_health(req: dict) -> dict:
    from cognee.api.v1.health.health import health_checker
    h = run(health_checker.get_health_status(detailed=False))
    comps = {k: {"status": v.status.value, "details": v.details[:160]} for k, v in h.components.items()}
    ds = run(_dataset())
    return {"ok": True, "status": h.status.value, "components": comps, "dataset_exists": ds is not None}


def op_add(req: dict) -> dict:
    """Add items through cognee.add (DataItem, external_metadata carries the
    date), then cognify the dataset: the add + cognify that remember() runs."""
    from cognee.tasks.ingestion.data_item import DataItem
    items = []
    for it in req["items"]:
        meta = {k: v for k, v in (it.get("meta") or {}).items() if v}
        items.append(DataItem(data=it["text"], external_metadata=meta or None))
    t0 = time.perf_counter()
    res = run(cognee.add(items if len(items) > 1 else items[0], dataset_name=DATASET))
    info = getattr(res, "data_ingestion_info", None) or []
    ids = [str(x.get("data_id")) if isinstance(x, dict) and x.get("data_id") else None for x in info]
    add_s = time.perf_counter() - t0
    for i, it in zip(ids, req["items"]):
        if i:
            _texts[i] = it["text"]
    t1 = time.perf_counter()
    if req.get("cognify", True):
        run(cognee.cognify(datasets=[DATASET]))
    return {"ok": True, "ids": ids, "add_s": round(add_s, 2), "cognify_s": round(time.perf_counter() - t1, 2)}


def op_cognify(req: dict) -> dict:
    t0 = time.perf_counter()
    run(cognee.cognify(datasets=[DATASET]))
    return {"ok": True, "s": round(time.perf_counter() - t0, 2)}


def op_recall(req: dict) -> dict:
    """cognee.recall as a client calls it, per door:
      recall         no query_type: keyless, cognee picks CHUNKS itself
      graph_context  GRAPH_COMPLETION, only_context=True
      context        cognee's own routing (no query_type), only_context=True:
                     the context its answer model receives, with the date of
                     each passage (include_external_metadata, key 'date')
      answer         the same, with the answer composed by the LLM
      chunks         CHUNKS: the vector hits alone"""
    from cognee import SearchType
    door = req.get("door") or "recall"
    # a fresh session per call: no earlier question or answer comes back
    kw: dict = {"datasets": [DATASET], "session_id": f"adebench-{uuid.uuid4().hex}"}
    if door in ("recall", "graph_context", "chunks"):
        kw["top_k"] = int(req.get("top_k") or 15)
    if door == "graph_context":
        kw.update(query_type=SearchType.GRAPH_COMPLETION, only_context=True)
    elif door == "chunks":
        kw.update(query_type=SearchType.CHUNKS)
    elif door in ("context", "answer"):
        kw["retriever_specific_config"] = {"include_external_metadata": True, "external_metadata_keys": ["date"]}
        if door == "context":
            kw["only_context"] = True
    t0 = time.perf_counter()
    res = run(cognee.recall(req["q"], **kw))
    ms = (time.perf_counter() - t0) * 1000
    hits = []
    for e in res or []:
        raw = getattr(e, "raw", None) or {}
        md = getattr(e, "metadata", None) or {}
        text = getattr(e, "text", None)
        if text is None and isinstance(e, dict):
            text, raw = e.get("text"), e
        raw = raw if isinstance(raw, dict) else {}
        hits.append({"text": str(text or ""), "score": getattr(e, "score", None),
                     "search_type": str(getattr(e, "search_type", "") or ""),
                     "kind": str(getattr(e, "kind", "") or ""),
                     "data_id": str(md.get("data_id") or raw.get("document_id") or ""),
                     "external_metadata": _meta(raw.get("external_metadata")),
                     "created_at": raw.get("created_at")})
    return {"ok": True, "hits": hits, "ms": ms}


def _rows() -> list[dict]:
    ds = run(_dataset())
    if ds is None:
        return []
    out = []
    for r in run(cognee.datasets.list_data(ds.id)):
        rid = str(r.id)
        if rid not in _texts:
            _texts[rid] = _read_location(getattr(r, "raw_data_location", "") or "")
        out.append({"id": rid, "text": _texts[rid], "meta": _meta(getattr(r, "external_metadata", None)),
                    "created_at": str(getattr(r, "created_at", "") or "")})
    return out


def op_rows(req: dict) -> dict:
    return {"ok": True, "rows": _rows()}


def op_forget(req: dict) -> dict:
    from uuid import UUID
    ds = run(_dataset())
    if ds is None:
        return {"ok": False, "error": "dataset not found"}
    r = run(cognee.forget(data_id=UUID(req["id"]), dataset_id=ds.id))
    _texts.pop(req["id"], None)
    return {"ok": str((r or {}).get("status")) == "success", "result": json.loads(json.dumps(r, default=str))}


def _graph():
    from cognee.context_global_variables import set_database_global_context_variables
    from cognee.infrastructure.databases.graph import get_graph_engine
    ds = run(_dataset())
    if ds is None:
        return [], []

    async def _read():
        async with set_database_global_context_variables(ds.id, ds.owner_id):
            g = await get_graph_engine()
            return await g.get_graph_data()
    return run(_read())


def op_graph(req: dict) -> dict:
    nodes, edges = _graph()
    by_type: dict[str, int] = {}
    for _, p in nodes:
        t = str(p.get("type") or "?")
        by_type[t] = by_type.get(t, 0) + 1
    rels: dict[str, int] = {}
    superseded = contradicts = 0
    for e in edges:
        p = e[3] if len(e) > 3 and isinstance(e[3], dict) else {}
        r = str(p.get("relationship_name") or e[2])
        rels[r] = rels.get(r, 0) + 1
        if any("supersed" in str(k).lower() and v for k, v in p.items()):
            superseded += 1
        contradicts += r == "contradicts"
    data_ids = {r["id"] for r in _rows()}
    chunks = [(nid, p) for nid, p in nodes if p.get("type") == "DocumentChunk"]
    orphan_chunks = sum(1 for _, p in chunks if str(p.get("document_id") or "") not in data_ids)
    touched = {str(e[0]) for e in edges} | {str(e[1]) for e in edges}
    lonely_entities = sum(1 for nid, p in nodes if p.get("type") == "Entity" and str(nid) not in touched)
    return {"ok": True, "nodes": len(nodes), "edges": len(edges), "nodes_by_type": by_type,
            "edges_by_relationship": rels, "superseded_edges": superseded, "contradicts_edges": contradicts,
            "chunk_nodes": len(chunks), "orphan_chunk_nodes": orphan_chunks,
            "entities_without_edges": lonely_entities, "data_items": len(data_ids)}


def op_entity_edges(req: dict) -> dict:
    low = req["entity"].lower().replace("_", " ").strip()
    nodes, edges = _graph()
    ids = {str(nid) for nid, p in nodes if p.get("type") == "Entity" and str(p.get("name") or "").lower() == low}
    n = sum(1 for e in edges if str(e[0]) in ids or str(e[1]) in ids)
    return {"ok": True, "edges": n, "nodes": len(ids)}


OPS = {"init": op_init, "health": op_health, "add": op_add, "cognify": op_cognify, "recall": op_recall,
       "rows": op_rows, "forget": op_forget, "graph": op_graph, "entity_edges": op_entity_edges,
       "usage": op_usage, "ping": lambda r: {"ok": True}}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            op = OPS[req["op"]]
            if cognee is None and req["op"] not in ("init", "ping"):
                ans = {"ok": False, "error": "not initialised"}
            else:
                ans = op(req)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            ans = {"ok": False, "error": f"{type(e).__name__}: {e}"[:500]}
        _out.write(json.dumps(ans, default=str) + "\n")
        _out.flush()
        try:
            _save_usage()
        except OSError:
            pass


if __name__ == "__main__":
    main()
