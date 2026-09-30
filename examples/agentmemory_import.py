"""Put the synthetic memory (examples/synthetic.py) into an agentmemory store,
so that the same golden set runs there too:

    EMBEDDING_PROVIDER=local AGENTMEMORY_DATA_DIR=/scratch/agentmemory agentmemory
    AGENTMEMORY_URL=http://127.0.0.1:3111 python examples/agentmemory_import.py
    ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.agentmemory:AgentmemoryAdapter \\
        --cases sets/quick/cases --history /tmp/agentmemory-run --write-back

Nothing is rewritten on the way in. A card is one memory dated with the
card's date and a fact with an event date is one memory with that date, both
through agentmemory's own export/import (the only write that keeps a date);
a fact without a date and an alias (a sentence saying what the alias means)
go through memory_save, which stamps the time of the save. An episode is a
two-turn transcript, the request and the result at the episode's time,
through the transcript import (/replay/import-jsonl), one session each. With
an LLM provider configured, the graph is then built (/graph/build) and the
consolidation run (/consolidate-pipeline). The store is a scratch one.

The set is sets/quick unless --set <folder> (or ADEBENCH_SET) names another one.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adebench.agentmemory import AgentmemoryAdapter  # noqa: E402
from adebench import sets  # noqa: E402

_C = sets.current().constants()  # --set <folder> or ADEBENCH_SET; default sets/quick
CARDS, CARD_DATES, FACTS, ALIASES, EPISODES = _C["CARDS"], _C["CARD_DATES"], _C["FACTS"], _C["ALIASES"], _C["EPISODES"]


def main() -> int:
    a = AgentmemoryAdapter()
    if not a.health():
        print(f"agentmemory does not answer at {a.url}")
        return 2
    dated = [(text, CARD_DATES[entity]) for entity, text in CARDS.items()]
    dated += [(f["content"], f["event_date"]) for f in FACTS if f["event_date"]]
    n = len(a.import_memories(dated))
    for f in FACTS:
        if not f["event_date"]:
            n += bool(a.save(f["content"]))
    for al in ALIASES:
        n += bool(a.save(f"'{al['alias'].replace('_', ' ')}' is another name for {al['canonical']}."))
    obs = 0
    for i, e in enumerate(EPISODES):
        out = a.import_transcript(f"adebench-episode-{i}", [("user", e["input_summary"], e["created_at"]),
                                                            ("assistant", e["output_summary"], e["created_at"])])
        obs += int(out.get("observations") or 0)
    print(f"stored {n} memories and {len(EPISODES)} episodes ({obs} observations)")
    # With an LLM provider configured ("with Gemini" mode) the transcript
    # import does not run the model: the graph is built and the consolidation
    # run through their own REST routes, as for any imported corpus. Keyless,
    # both need the model and are not called.
    flags = a._http("GET", "/agentmemory/config/flags")
    if flags.get("provider") not in (None, "noop"):
        print("provider:", flags.get("provider"), "embeddings:", flags.get("embeddingProvider"))
        print("graph/build:", a._http("POST", "/agentmemory/graph/build", {}, timeout=900))
        print("consolidate-pipeline:", str(a._http("POST", "/agentmemory/consolidate-pipeline", {},
                                                     timeout=900))[:600])
    print("trace:", a.update_trace(), "dated:", a.event_date_share())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
