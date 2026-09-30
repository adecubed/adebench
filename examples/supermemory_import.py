"""Put the synthetic memory (examples/synthetic.py) into a supermemory local
server, so that the same golden set runs there too:

    SUPERMEMORY_DATA_DIR=<empty scratch dir> PORT=3951 GEMINI_API_KEY=<key> supermemory-server
    python examples/supermemory_import.py
    ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.supermemory:SupermemoryAdapter \\
        --cases examples/synthetic_data/cases --history /tmp/supermemory-run --no-sandbox-test --write-back

Nothing is rewritten on the way in. Everything goes through the historical
backfill path (`POST /v3/documents/batch`), sorted oldest to newest as the
docs ask, one document per call, each processed before the next: a card is one document dated with the
card's date; a fact is one document with its event date (none when the fact
has none: no date is invented); an episode is one conversation document,
"user: <request>\\nassistant: <result>", at the episode's time; an alias is a
sentence saying what the alias means, undated. Episodes carry the metadata
kind=episode, so the adapter can list them for the time section. Then the
script waits until supermemory's memory agent has processed every document.
The container is a scratch one; use an empty data dir for a fresh store.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adebench.supermemory import SupermemoryAdapter, _iso  # noqa: E402
from examples.synthetic import ALIASES, CARD_DATES, CARDS, EPISODES, FACTS  # noqa: E402


def main() -> int:
    a = SupermemoryAdapter()
    if not a.health():
        print(f"supermemory does not answer at {a.base}")
        return 2
    if a._documents():
        print(f"container {a.container!r} is not empty: use a fresh store")
        return 2
    dated: list[dict] = []
    undated: list[dict] = []
    for entity, text in CARDS.items():
        dated.append({"content": text, "documentDate": _iso(CARD_DATES[entity])})
    for f in FACTS:
        if f["event_date"]:
            dated.append({"content": f["content"], "documentDate": _iso(f["event_date"])})
        else:
            undated.append({"content": f["content"]})
    for al in ALIASES:
        undated.append({"content": f"'{al['alias'].replace('_', ' ')}' is another name for {al['canonical']}."})
    for e in EPISODES:
        dated.append({"content": f"user: {e['input_summary']}\nassistant: {e['output_summary']}",
                      "documentDate": _iso(e["created_at"]), "metadata": {"kind": "episode"}})
    dated.sort(key=lambda d: d["documentDate"])
    docs = dated + undated
    t0 = time.perf_counter()
    by: dict[str, int] = {}
    # One document per batch call, each processed before the next is sent.
    # supermemory-server 0.0.8 (windows-x64) accepted a 21-document batch and
    # then stalled all 21 in the "maintain-container-description" step, with
    # no LLM call and no CPU, for good. Sequential also keeps the order the
    # docs ask for, so the memory agent sees the older fact first.
    for i, doc in enumerate(docs, 1):
        ids = a.add_batch([doc])
        states = a.wait_done(ids, max_s=1800)
        for s in states.values():
            by[s] = by.get(s, 0) + 1
        print(f"{i}/{len(docs)} {list(states.values())} {time.perf_counter() - t0:.0f} s  {doc['content'][:50]!r}",
              flush=True)
    print(f"processed in {time.perf_counter() - t0:.0f} s: {by}")
    print("memories:", a.update_trace())
    return 0 if by.get("done") == len(docs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
