"""Put the synthetic memory (examples/synthetic.py) into a fresh Jev-Mem store,
observation by observation, so that the same golden set runs there too:

    JEVMEM_HOME=... JEVMEM_PYTHON=... python examples/jevmem_import.py
    python -m adebench --adapter adebench.jevmem:JevMemAdapter \
        --cases sets/quick/cases --history /tmp/jevmem-run

Nothing is rewritten on the way in. Each card, fact, alias and episode is one
observation through Jev-Mem's explicit write path (MemoryBuilder.build: typing,
candidates, relation judgments by the System-One model, insertion), with its
own date. What becomes a link is Jev-Mem's decision. The store is emptied
first: it is a benchmark load, not someone's memory.

The set is sets/quick unless --set <folder> (or ADEBENCH_SET) names another one.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adebench import jevmem  # noqa: E402
from adebench import sets  # noqa: E402

_C = sets.current().constants()  # --set <folder> or ADEBENCH_SET; default sets/quick
CARDS, CARD_DATES, FACTS, ALIASES, EPISODES = _C["CARDS"], _C["CARD_DATES"], _C["FACTS"], _C["ALIASES"], _C["EPISODES"]


def main() -> int:
    if not jevmem.STORE:
        print("set JEVMEM_HOME and JEVMEM_PYTHON")
        return 2
    shutil.rmtree(jevmem.STORE, ignore_errors=True)
    t0 = time.time()
    j = jevmem.JevMemAdapter(fresh=True)
    info = j._bridge().info
    print(f"bridge up in {time.time() - t0:.0f}s: backend {info.get('backend')} {info.get('model') or ''}")
    items = []
    for entity, text in CARDS.items():
        items.append({"content": text, "timestamp": f"{CARD_DATES[entity]}T12:00:00",
                      "metadata": {"kind": "card", "key": entity}})
    for f in FACTS:
        items.append({"content": f["content"],
                      "timestamp": f"{f['event_date']}T12:00:00" if f["event_date"] else None,
                      "metadata": {"kind": "fact", "key": f["key"]}})
    for al in ALIASES:
        items.append({"content": f"'{al['alias'].replace('_', ' ')}' is another name for {al['canonical']}.",
                      "timestamp": None, "metadata": {"kind": "alias", "key": al["alias"]}})
    for e in EPISODES:
        items.append({"content": f"{e['input_summary']}. Result: {e['output_summary']}",
                      "timestamp": e["created_at"], "metadata": {"kind": "episode", "key": e["repl"]}})
    t0 = time.time()
    ids = j.build(items)
    kept = sum(1 for i in ids if i)
    print(f"{kept} of {len(items)} observations admitted in {time.time() - t0:.0f}s -> {jevmem.STORE}")
    print("links:", j.update_trace()["links_by_type"])
    j._b.close()
    return 0 if kept else 1


if __name__ == "__main__":
    raise SystemExit(main())
