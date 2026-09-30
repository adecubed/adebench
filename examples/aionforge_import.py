"""Put the synthetic memory (examples/synthetic.py) into an Aionforge Memory
store, capture by capture, so that the same golden set runs there too:

    docker run --network host ghcr.io/jscott3201/aionforge-memory:0.4.0 \\
        --config /config.toml serve http --listen 127.0.0.1:3918
    AIONFORGE_URL=http://127.0.0.1:3918/mcp python examples/aionforge_import.py
    python -m adebench --adapter adebench.aionforge:AionforgeAdapter \\
        --cases sets/quick/cases --history /tmp/aionforge-run

Nothing is rewritten on the way in. A card is one capture, dated with the
card's date; a fact is one capture with its event date; an episode is two
captures, the request and the result, at the episode's time; an alias is a
sentence saying what the alias means. All of it in one session (so the time
section can list it) and in the agent's private namespace. At the end a few
consolidation ticks derive Aionforge's own facts and entities; the store is
a scratch one.

The set is sets/quick unless --set <folder> (or ADEBENCH_SET) names another one.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adebench.aionforge import AionforgeAdapter  # noqa: E402
from adebench import sets  # noqa: E402

_C = sets.current().constants()  # --set <folder> or ADEBENCH_SET; default sets/quick
CARDS, CARD_DATES, FACTS, ALIASES, EPISODES = _C["CARDS"], _C["CARD_DATES"], _C["FACTS"], _C["ALIASES"], _C["EPISODES"]


def main() -> int:
    a = AionforgeAdapter()
    if not a.health():
        print(f"Aionforge does not answer at {a.url}")
        return 2
    n = 0
    for entity, text in CARDS.items():
        n += bool(a.capture(text, when=CARD_DATES[entity], role="user"))
    for f in FACTS:
        n += bool(a.capture(f["content"], when=f["event_date"], role="user"))
    for al in ALIASES:
        n += bool(a.capture(f"'{al['alias'].replace('_', ' ')}' is another name for {al['canonical']}.", role="user"))
    for e in EPISODES:
        n += bool(a.capture(e["input_summary"], when=e["created_at"] + "Z", role="user"))
        n += bool(a.capture(e["output_summary"], when=e["created_at"] + "Z", role="assistant"))
    c = a.consolidate(5)
    print(f"captured {n} memories; consolidate: {c}")
    print("census:", a.update_trace().get("census"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
