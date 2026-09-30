"""Put the synthetic memory (examples/synthetic.py) into a Memoose dataset,
so that the same golden set runs there too:

    pip install memoose
    python examples/memoose_import.py                 # writes into dataset 'adebench'
    python -m adebench --adapter adebench.memoose:MemooseAdapter \
        --cases sets/quick/cases --history /tmp/memoose-run

Nothing is rewritten on the way in. A card becomes an entity whose
description is the card, word for word. A fact becomes a relation from the
entity it belongs to, carrying its own sentence as the description and its
event date as valid_from, plus the same sentence as a chunk, which is how
Memoose finds text lexically. An episode becomes two turns of a session, on
the day it happened. An alias becomes what Memoose calls an alias: the
alias entity merged into the canonical one.

The dataset is a scratch one. `memoose -d adebench forget --all` removes it.

The set is sets/quick unless --set <folder> (or ADEBENCH_SET) names another one.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adebench.memoose import MemooseAdapter  # noqa: E402
from adebench import sets  # noqa: E402

_C = sets.current().constants()  # --set <folder> or ADEBENCH_SET; default sets/quick
CARDS, CARD_DATES, FACTS, ALIASES, EPISODES = _C["CARDS"], _C["CARD_DATES"], _C["FACTS"], _C["ALIASES"], _C["EPISODES"]

TYPES = {"brain": "System", "mailbox": "Product", "calendar": "Product", "owner": "Person"}


def main() -> int:
    m = MemooseAdapter()
    if not m.health():
        print("memoose does not answer: pip install memoose")
        return 2

    def tool(name: str, payload: dict) -> dict:
        return m._cli(["tool", name, "--stdin"], stdin=json.dumps(payload))

    kind = {e: TYPES.get(e, "Concept") for e in CARDS}   # the quick set's types; any other entity is a Concept
    for entity, text in CARDS.items():
        tool("remember", {"entities": [{"name": entity, "type": kind[entity], "description": text}],
                          "relations": [], "summary": text, "source_text": text,
                          "source": f"adebench:card:{entity}"})

    for f in FACTS:
        entity = sets.fact_entity(f, CARDS, "owner" if "owner" in CARDS else next(iter(CARDS)))
        tool("remember", {
            "entities": [{"name": entity, "type": kind[entity], "description": ""},
                         {"name": f["key"], "type": "Concept", "description": f["content"]}],
            "relations": [{"source": entity, "name": "records", "target": f["key"],
                           "description": f["content"], "valid_from": f["event_date"],
                           "evidence": f"adebench:fact:{f['key']}"}],
            "summary": f["content"], "source_text": f["content"],
            "source": f"adebench:fact:{f['key']}"})

    session = "adebench-import"
    m._cli(["session", "start", session])
    for e in EPISODES:
        # Memoose stamps a turn with the moment it is written: a session has no
        # way to say when a turn happened, so the episodes arrive dated today
        # and the day-filter case measures that, honestly.
        for role, text in (("user", f"[{e['created_at'][:10]}] {e['input_summary']}"),
                           ("assistant", e["output_summary"])):
            m._cli(["session", "turn", session, "--role", role, "--text", text])

    for a in ALIASES:
        tool("remember", {"entities": [{"name": a["alias"], "type": kind.get(a["canonical"], "Concept"),
                                        "description": ""}], "relations": []})
        tool("merge_entities", {"keep": a["canonical"], "drop": a["alias"]})

    counts = m.graph_counts()
    print(f"dataset {m.dataset}: {counts.get('nodes')} entities, {counts.get('edges')} facts, "
          f"{len(EPISODES)} episodes, card dates {len(CARD_DATES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
