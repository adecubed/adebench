"""The Jev-Mem side of the adebench adapter: one process, run with Jev-Mem's
own Python, that keeps the models loaded and answers JSON lines on stdin.

    <jev-mem venv>/python -m adebench.jevmem_bridge   (started by adebench.jevmem)

It imports nothing from adebench and nothing adebench imports from it: the
harness stays dependency-free, Jev-Mem stays in its own environment. Every
request is one line {"op": ..., ...}; every answer one line {"ok": ..., ...}.
Logging goes to stderr, so stdout carries answers only.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

HOME = Path(os.environ.get("JEVMEM_HOME", ".")).resolve()
os.environ.setdefault("USE_TF", "0")
# the benchmark measures what the memory hands over: no answer model
os.environ.pop("OPENAI_API_KEY", None)
sys.path.insert(0, str(HOME))
os.chdir(HOME)

_out = sys.stdout
sys.stdout = sys.stderr  # Jev-Mem prints; keep the answer channel clean

system = None


def _node_dict(n) -> dict:
    a = dict(getattr(n, "attributes", {}) or {})
    meta = a.get("metadata") if isinstance(a.get("metadata"), dict) else {}
    return {
        "id": n.node_id,
        "content": str(a.get("raw_content") or n.content_narrative or ""),
        "timestamp": n.timestamp.isoformat() if getattr(n, "timestamp", None) else None,
        "kind": str(meta.get("kind") or a.get("kind") or ""),
        "key": str(meta.get("key") or a.get("key") or ""),
        "memory_type": str(a.get("memory_type") or a.get("jev_type") or ""),
    }


def op_init(req: dict) -> dict:
    global system
    from jev_mem.system import JevMemSystem
    from memory.jev_mem_config import JevMemConfig
    overrides = {}
    if req.get("device"):
        overrides["laya_device"] = req["device"]
    cfg = JevMemConfig.load(req.get("config") or "config/laya_mem.json", **overrides)
    cache = Path(req["cache_dir"])
    t0 = time.perf_counter()
    system = JevMemSystem(model="gpt-4o-mini", embedding_model=req.get("embedding") or "minilm",
                          cache_dir=str(cache), jev_config=cfg)
    loaded = False
    if not req.get("fresh") and (cache / "graph.json").exists():
        system.load_memory()
        loaded = True
    return {"ok": True, "loaded": loaded, "nodes": len(system.graph_db.nodes),
            "backend": getattr(cfg, "decision_backend", "jev"), "model": getattr(cfg, "laya_model", None),
            "init_s": round(time.perf_counter() - t0, 1)}


def op_build(req: dict) -> dict:
    ids = []
    for item in req["items"]:
        ts = item.get("timestamp")
        if isinstance(ts, str) and ts:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        node = system.memory_builder.build(item["content"], ts or None, item.get("metadata") or {})
        ids.append(getattr(node, "node_id", None))
    if req.get("save", True):
        system.save_memory()
    return {"ok": True, "ids": ids}


def op_query(req: dict) -> dict:
    t0 = time.perf_counter()
    ctx, evidence = system.query_engine.query(req["q"], top_k=int(req.get("top_k") or 5))
    md = dict(getattr(ctx, "metadata", {}) or {})
    keep = {k: md.get(k) for k in ("controller", "decision_backend", "stopping_decision", "jev_calls",
                                   "nodes_visited", "top_k_returned", "graph_needs", "fallback_events",
                                   "retrieved_dia_ids", "latency_seconds")}
    return {"ok": True, "evidence": evidence if isinstance(evidence, str) else json.dumps(evidence, default=str),
            "metadata": json.loads(json.dumps(keep, default=str)), "ms": (time.perf_counter() - t0) * 1000}


def op_nodes(req: dict) -> dict:
    return {"ok": True, "nodes": [_node_dict(n) for n in system.graph_db.nodes.values()
                                  if getattr(n, "content_narrative", None) is not None]}


def op_delete(req: dict) -> dict:
    """Jev-Mem has no forget: the node goes, with its links, its vector and
    its keyword-index entries, and the store is saved."""
    nid = req["id"]
    ok = bool(system.graph_db.delete_node(nid))
    try:
        system.vector_db.delete_vector(nid)
    except Exception:  # noqa: BLE001
        pass
    for ids in system.memory_builder.node_index.values():
        if isinstance(ids, set):
            ids.discard(nid)
    system.query_engine.node_index = system.memory_builder.node_index
    system.save_memory()
    return {"ok": ok}


def op_links(req: dict) -> dict:
    counts: dict[str, int] = {}
    g = system.graph_db
    store = getattr(g, "links", None)
    items = store.values() if isinstance(store, dict) else (store or [])
    for link in items:
        t = getattr(getattr(link, "link_type", None), "name", str(getattr(link, "link_type", "?")))
        sub = (getattr(link, "properties", None) or {}).get("sub_type") or ""
        k = f"{t}:{sub}" if sub else t
        counts[k] = counts.get(k, 0) + 1
    return {"ok": True, "links": counts}


def op_node_links(req: dict) -> dict:
    """Links touching the nodes whose text mentions an entity."""
    low = req["entity"].lower().replace("_", " ")
    ids = {n.node_id for n in system.graph_db.nodes.values()
           if low in str(getattr(n, "content_narrative", "") or "").lower()}
    store = getattr(system.graph_db, "links", None)
    items = store.values() if isinstance(store, dict) else (store or [])
    n = sum(1 for link in items if getattr(link, "source_node_id", None) in ids or getattr(link, "target_node_id", None) in ids)
    return {"ok": True, "edges": n, "nodes": len(ids)}


OPS = {"init": op_init, "build": op_build, "query": op_query, "nodes": op_nodes, "delete": op_delete,
       "links": op_links, "node_links": op_node_links, "ping": lambda r: {"ok": True}}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            op = OPS[req["op"]]
            if system is None and req["op"] not in ("init", "ping"):
                ans = {"ok": False, "error": "not initialised"}
            else:
                ans = op(req)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc(file=sys.stderr)
            ans = {"ok": False, "error": f"{type(e).__name__}: {e}"[:500]}
        _out.write(json.dumps(ans, default=str) + "\n")
        _out.flush()


if __name__ == "__main__":
    main()
