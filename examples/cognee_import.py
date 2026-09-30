"""Put the synthetic memory (examples/synthetic.py) into a fresh cognee store,
item by item, so that the same golden set runs there too:

    COGNEE_HOME=... COGNEE_PYTHON=... python examples/cognee_import.py      (Gemini, GOOGLE_API_KEY)
    COGNEE_LLM=gliner_demo ... python examples/cognee_import.py            (local, no key)
    ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.cognee:CogneeAdapter \\
        --cases examples/synthetic_data/cases --history /tmp/cognee-run --no-sandbox-test --write-back

Nothing is rewritten on the way in. Each card, fact, alias and episode is one
data item through cognee.add (a DataItem whose external_metadata carries the
item's own date, and its kind), then one cognify over the dataset: chunking,
extraction of entities and relations (Gemini, or the local GLiNER demo),
summaries, embeddings. What
becomes a node or an edge is cognee's decision. An alias is a sentence saying
what the alias means; an episode is its request and its result in one item.
The store is emptied first (prune): it is a benchmark load, not someone's
memory.
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adebench import cognee  # noqa: E402
from examples.synthetic import ALIASES, CARD_DATES, CARDS, EPISODES, FACTS  # noqa: E402


def main() -> int:
    if not cognee.STORE:
        print("set COGNEE_HOME and COGNEE_PYTHON")
        return 2
    shutil.rmtree(cognee.STORE, ignore_errors=True)
    t0 = time.time()
    c = cognee.CogneeAdapter(fresh=True)
    info = c._bridge().info
    print(f"bridge up in {time.time() - t0:.0f}s: cognee {info.get('cognee_version')}, llm {info.get('llm')}, extractor "
          f"{info.get('extractor')}, embeddings {info.get('embedding')}, {info.get('vector_db')} + {info.get('graph_db')}")
    items = []
    for entity, text in CARDS.items():
        items.append({"text": text, "meta": {"date": CARD_DATES[entity], "kind": "card"}})
    for f in FACTS:
        items.append({"text": f["content"], "meta": {"date": f["event_date"], "kind": "fact"}})
    for al in ALIASES:
        items.append({"text": f"'{al['alias'].replace('_', ' ')}' is another name for {al['canonical']}.",
                      "meta": {"kind": "alias"}})
    for e in EPISODES:
        items.append({"text": f"{e['input_summary']}. Result: {e['output_summary']}",
                      "meta": {"date": e["created_at"], "kind": "episode"}})
    t0 = time.time()
    ids = c.add(items)
    kept = sum(1 for i in ids if i)
    print(f"{kept} of {len(items)} items added and cognified in {time.time() - t0:.0f}s -> {cognee.STORE}")
    print("graph:", c.graph_counts())
    if cognee.MODE == "gemini":
        print("LLM/embedding calls of the import:", c.usage())
    c._b.close()
    return 0 if kept == len(items) else 1


if __name__ == "__main__":
    raise SystemExit(main())
