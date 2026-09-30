"""Put the synthetic memory (examples/synthetic.py) into a Hindsight bank,
retain by retain, so that the same golden set runs there too:

    HINDSIGHT_URL=http://127.0.0.1:8888 python examples/hindsight_import.py
    python -m adebench --adapter adebench.hindsight:HindsightAdapter \\
        --cases sets/quick/cases --history /tmp/hindsight-run

Nothing is rewritten on the way in. A card is one retain dated with the
card's date; a fact one retain with its event date; an episode one retain,
request and result, at the episode's time; an alias a sentence saying what
the alias means. What each retain becomes (world facts, experiences,
entities) is Hindsight's extractor's business, and the report says which
model ran it. The bank is a scratch one: it is emptied first.

The set is sets/quick unless --set <folder> (or ADEBENCH_SET) names another one.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adebench.hindsight import HindsightAdapter, HindsightError  # noqa: E402
from adebench import sets  # noqa: E402

_C = sets.current().constants()  # --set <folder> or ADEBENCH_SET; default sets/quick
CARDS, CARD_DATES, FACTS, ALIASES, EPISODES = _C["CARDS"], _C["CARD_DATES"], _C["FACTS"], _C["ALIASES"], _C["EPISODES"]


def main() -> int:
    h = HindsightAdapter()
    if not h.health():
        print(f"Hindsight does not answer at {h.base}")
        return 2
    try:
        h._tool("clear_memories", {})
    except HindsightError as e:
        print("clear_memories:", str(e)[:120])
    items: list[tuple[str, str | None, str]] = []
    for entity, text in CARDS.items():
        items.append((text, CARD_DATES[entity], f"card-{entity}"))
    for f in FACTS:
        items.append((f["content"], f["event_date"], f"fact-{f['key']}"))
    for al in ALIASES:
        items.append((f"'{al['alias'].replace('_', ' ')}' is another name for {al['canonical']}.", None, f"alias-{al['alias']}"))
    for i, e in enumerate(EPISODES):
        items.append((f"{e['input_summary']}. Result: {e['output_summary']}", e["created_at"], f"episode-{i}"))
    n_mem = 0
    for i, (text, when, doc) in enumerate(items, 1):
        t0 = time.time()
        for attempt in range(3):
            try:
                _, ids = h.retain(text, when=when, document_id=f"adebench-{doc}")
                break
            except HindsightError as e:
                ids = []
                print(f"   retry {attempt + 1}: {str(e)[:100]}")
                time.sleep(5)
        n_mem += len(ids)
        print(f"{i:2}/{len(items)} ({time.time() - t0:.0f}s) {len(ids)} memories <- {text[:60]!r}")
    print(f"bank {h.bank}: {n_mem} memories from {len(items)} retains; by type: {h.update_trace()['memories_by_type']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
