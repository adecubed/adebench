"""Put the synthetic memory (examples/synthetic.py) into an Engram store, so
that the same golden set runs there too:

    set ENGRAM_BIN=C:/.../engram.exe
    set ENGRAM_DATA_DIR=C:/.../engram-data     # a fresh, scratch store
    python examples/engram_import.py
    python -m adebench --adapter adebench.engram:EngramAdapter \\
        --cases sets/quick/cases --history /tmp/engram-run

Nothing is rewritten on the way in. Everything that has a date goes through
Engram's own import path (`engram import`, the restore of an export), because
that is the only way Engram keeps a time that is not the write time:
  - a card is one observation titled with its entity's name, the card word
    for word as content, at the card's date
  - a fact is one observation, its sentence as content, at its event date;
    its title is what Engram itself derives from a text that has none (the
    first 60 characters), so for these short sentences it is the sentence
  - an episode is a session of its own with the user's prompt (the request)
    and one observation (the request as title, the result as content), at the
    episode's time
What has no date goes through `mem_save`, the way an agent writes, and is
stamped with the write time: the two 'travel' facts, and the aliases, each a
sentence saying what the alias means, titled the same way. All of it in
project 'adebench'.

The set is sets/quick unless --set <folder> (or ADEBENCH_SET) names another one.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adebench.engram import EngramAdapter, title_of  # noqa: E402
from adebench import sets  # noqa: E402

_C = sets.current().constants()  # --set <folder> or ADEBENCH_SET; default sets/quick
CARDS, CARD_DATES, FACTS, ALIASES, EPISODES = _C["CARDS"], _C["CARD_DATES"], _C["FACTS"], _C["ALIASES"], _C["EPISODES"]


def main() -> int:
    a = EngramAdapter()
    if not a.health():
        print(f"Engram does not answer ({a.bin} mcp, data dir {a.data_dir})")
        return 2
    records = []
    for entity, text in CARDS.items():
        records.append(a.export_record(entity, text, CARD_DATES[entity], "adebench-import", a.project))
    undated = []
    for f in FACTS:
        if f["event_date"]:
            records.append(a.export_record(title_of(f["content"]), f["content"], f["event_date"], "adebench-import", a.project))
        else:
            undated.append(f["content"])
    for i, e in enumerate(EPISODES):
        records.append(a.export_record(e["input_summary"], e["output_summary"], e["created_at"],
                                       f"adebench-episode-{i + 1}", a.project, prompt=e["input_summary"]))
    print(a.import_export(a.export_file(records)).strip())
    n = len(records)
    for text in undated:
        n += bool(a.save(title_of(text), text))
    for al in ALIASES:
        sentence = f"'{al['alias'].replace('_', ' ')}' is another name for {al['canonical']}."
        n += bool(a.save(title_of(sentence), sentence))
    print(f"{n} observations written; trace: {a.update_trace()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
