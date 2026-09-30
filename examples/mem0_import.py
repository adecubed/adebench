"""Put the synthetic memory (examples/synthetic.py) into a fresh mem0 store,
item by item, so that the same golden set runs there too:

    MEM0_HOME=... MEM0_PYTHON=... python examples/mem0_import.py
    ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.mem0:Mem0Adapter \\
        --cases sets/quick/cases --history /tmp/mem0-run --no-sandbox-test --write-back

Nothing is rewritten on the way in. Each card, fact, alias and episode is one
Memory.add with infer=True, mem0's normal path: its LLM (Gemini) decides what
memories to extract from it, how to word them, and what it already has. A
card, a fact and an alias are one user message; an episode is what it was, an
exchange: its request as the user message and its result as the assistant's.
An alias is a sentence saying what the alias means.

Dates: mem0 OSS has no event time. Memory.add's `timestamp` is platform-only
(it raises in OSS) and the extraction is told that today is the observation
date. The item's own date (card update, fact event date, episode time) is
carried as mem0 metadata {"date": ...}, as given; an item without a date
(the two travel facts, the aliases) gets none. The metadata also carries the
item's kind. No date is invented.

The store is emptied first (the whole MEM0_STORE folder): it is a benchmark
load, not someone's memory. Only a folder that is empty or holds nothing but
a mem0 store (history.db, qdrant/, mem0_dir/) is removed; anything else and the
import refuses. Re-import before EACH benchmark run: mem0 keeps the session's
saved messages and reads them at the next m.add, so the probes of one run
would otherwise reach the next.

The set is sets/quick unless --set <folder> (or ADEBENCH_SET) names another one.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adebench import mem0  # noqa: E402
from adebench import sets  # noqa: E402

_C = sets.current().constants()  # --set <folder> or ADEBENCH_SET; default sets/quick
CARDS, CARD_DATES, FACTS, ALIASES, EPISODES = _C["CARDS"], _C["CARD_DATES"], _C["FACTS"], _C["ALIASES"], _C["EPISODES"]


MEM0_STORE_ENTRIES = {"history.db", "history.db-journal", "history.db-wal", "history.db-shm", "qdrant", "mem0_dir"}


def is_mem0_store(path: Path) -> bool:
    """True for a missing or empty folder, or one holding only what mem0 writes."""
    if not path.exists():
        return True
    if not path.is_dir():
        return False
    return {p.name for p in path.iterdir()} <= MEM0_STORE_ENTRIES


def main() -> int:
    if not mem0.STORE:
        print("set MEM0_HOME and MEM0_PYTHON")
        return 2
    store = Path(mem0.STORE)
    if not is_mem0_store(store):
        print(f"refusing to empty {store}: it holds more than a mem0 store")
        return 2
    # a bridge of the previous run may still hold the files for a moment
    # (Windows locks them): a store that is not really gone would turn the
    # import into writes on top of the old memories, which mem0 dedups away
    for _ in range(30):
        shutil.rmtree(store, ignore_errors=True)
        if not store.exists():
            break
        time.sleep(1)
    else:
        print(f"could not empty {store}: files still in use (a mem0 bridge still running?)")
        return 2
    t0 = time.time()
    m = mem0.Mem0Adapter()
    info = m._bridge().info
    print(f"bridge up in {time.time() - t0:.0f}s: mem0 {info.get('mem0_version')}, llm {info.get('llm')}, "
          f"embedder {info.get('embedder')}, {info.get('vector_store')}, telemetry {info.get('telemetry')}")
    items = []
    for entity, text in CARDS.items():
        items.append((text, {"date": CARD_DATES[entity], "kind": "card"}))
    for f in FACTS:
        items.append((f["content"], {"date": f["event_date"], "kind": "fact"}))
    for al in ALIASES:
        items.append((f"'{al['alias'].replace('_', ' ')}' is another name for {al['canonical']}.",
                      {"kind": "alias"}))
    for e in EPISODES:
        items.append(([{"role": "user", "content": e["input_summary"]},
                       {"role": "assistant", "content": e["output_summary"]}],
                      {"date": e["created_at"], "kind": "episode"}))
    t0 = time.time()
    empty = truncated = 0
    for messages, meta in items:
        ids = m.add(messages, metadata=meta)
        empty += not ids
        finish = str(m.last_add.get("llm_finish") or "")
        truncated += "MAX_TOKENS" in finish
        print(f"  {meta.get('kind'):8} {len(ids)} memories  llm {finish.split('.')[-1] or '?'}  "
              f"{m.last_add.get('s')}s")
    rows = m.rows()
    print(f"{len(items)} items added in {time.time() - t0:.0f}s -> {len(rows)} memories "
          f"({empty} items produced none, {truncated} extractions cut at max_tokens) in {mem0.STORE}")
    for r in rows:
        print(f"  [{(r.get('metadata') or {}).get('kind')}] {mem0.hit_line(r)}")
    print("calls:", m.stats())
    print("entities:", m.graph_counts())
    m._b.close()
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
