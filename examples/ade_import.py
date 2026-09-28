"""Put the synthetic memory (examples/synthetic.py) into an EMPTY ADE Brain,
so that the Brain runs on the same golden set as the other memories:

    BRAIN_URL=http://127.0.0.1:8766 python examples/ade_import.py
    python -m adebench --adapter adebench.ade:AdeAdapter --cases examples/synthetic_data/cases \\
        --history /tmp/brain-synthetic-run

Nothing is rewritten on the way in. Every sentence, card text and fact
alike, goes through the Brain's fact path (POST /memory/semantic/learn:
dedup, supersession, vectors, with its event date, and with the entity the
fact is about, read from its key as the gbrain importer does, so the graph
gets its edges: the distiller extracts entities from an episode, a fact
loaded as text has to name them); an alias is registered
as an alias of its entity; an episode is recorded at its own time
(POST /memory/episodic/record with created_at). The Brain has no endpoint
that stores a card as given: a card is what the Brain writes from the facts
it holds, so after the load each entity's card is generated the Brain's
way (POST /memory/scheda/write without text), with the Brain's own model.
Run it against an instance whose memory is empty and whose BRAIN_LANG is
the golden set's language: it is a benchmark load, not a person's memory.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.synthetic import ALIASES, CARD_DATES, CARDS, EPISODES, FACTS  # noqa: E402

BRAIN = os.environ.get("BRAIN_URL", "http://127.0.0.1:8766").rstrip("/")
TOKEN = os.environ.get("BRAIN_TOKEN", "")


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(BRAIN + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {})},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def count() -> int:
    return int(json.loads(urllib.request.urlopen(BRAIN + "/memory/semantic/stats", timeout=10).read())["count"])


def main() -> int:
    try:
        n = count()
    except Exception as e:  # noqa: BLE001
        print(f"the Brain does not answer at {BRAIN}: {e}")
        return 2
    if n:
        print(f"the Brain at {BRAIN} already holds {n} facts: this importer wants an empty memory")
        return 3
    for entity, text in CARDS.items():
        r = post("/memory/semantic/learn", {"content": text, "event_date": CARD_DATES[entity],
                                            "key": f"card_text_{entity}", "entities": [entity]})
        print("card text", entity, "->", r.get("ok"))
    for f in FACTS:
        ent = f["key"].split("_", 1)[0]
        r = post("/memory/semantic/learn", {"content": f["content"], "event_date": f["event_date"], "key": f["key"],
                                            "entities": [ent] if ent in CARDS else []})
        print("fact", f["key"], "->", r.get("ok"), r.get("supersedes") or "")
    for al in ALIASES:
        r = post("/memory/scheda/write", {"entita": al["alias"], "alias_di": al["canonical"]})
        print("alias", al["alias"], "->", al["canonical"], r.get("ok"))
    for e in EPISODES:
        r = post("/memory/episodic/record", {"repl": e["repl"], "input_summary": e["input_summary"],
                                              "output_summary": e["output_summary"], "result": "ok",
                                              "created_at": e["created_at"]})
        print("episode", e["created_at"][:10], "->", r.get("ok"))
    for entity in CARDS:
        # the card is written by the Brain's model; when the model does not
        # answer (a 503 from the provider) the Brain says so and the load tries again
        for attempt in range(4):
            r = post("/memory/scheda/write", {"entita": entity})
            s = r.get("scheda") if isinstance(r.get("scheda"), dict) else {}
            if r.get("ok") and (s.get("content") or "").strip():
                break
            time.sleep(5)
        print("card generated", entity, "->", r.get("ok"), (s.get("content") or "")[:70])
    print(f"done: {count()} semantic rows (facts and cards), {len(EPISODES)} episodes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
