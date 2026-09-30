"""Put the synthetic memory (examples/synthetic.py) into a fresh memU store,
through memU's normal memorize path, so that the same golden set runs there too:

    MEMU_HOME=... MEMU_PYTHON=... python examples/memu_import.py
    ADEBENCH_LIVE_STATE_KEY= python -m adebench --adapter adebench.memu:MemuAdapter \\
        --cases examples/synthetic_data/cases --history /tmp/memu-run --no-sandbox-test --write-back

Nothing is rewritten on the way in. Each card, fact, alias and episode is one
session (memU's unit of input), sent in the order of cognee's import: a card
or a fact is one user message carrying its text; an alias is one user message
saying what the alias means (the sentence cognee's import uses); an episode is
its request as the user message and its result as the assistant message.
memU's input model accepts no timestamp, so the items' own dates do not go in
(a card's text already carries its "Updated" date; that stays as written).
memU prepares the jobs 10 sessions at a time, the executor (Gemini, see
adebench/memu.py) carries them out, memU commits. What becomes a wiki page, and
what is left out, is memU's executor's decision. The store is emptied first:
it is a benchmark load, not someone's memory.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adebench import memu  # noqa: E402
from examples.synthetic import ALIASES, CARDS, EPISODES, FACTS  # noqa: E402


def sessions() -> list[list[dict]]:
    out = []
    for text in CARDS.values():
        out.append([{"role": "user", "content": text}])
    for f in FACTS:
        out.append([{"role": "user", "content": f["content"]}])
    for al in ALIASES:
        out.append([{"role": "user", "content": f"'{al['alias'].replace('_', ' ')}' is another name for {al['canonical']}."}])
    for e in EPISODES:
        out.append([{"role": "user", "content": e["input_summary"]},
                    {"role": "assistant", "content": e["output_summary"]}])
    return out


def main() -> int:
    if not memu.STORE:
        print("set MEMU_HOME and MEMU_PYTHON")
        return 2
    shutil.rmtree(memu.STORE, ignore_errors=True)
    t0 = time.time()
    m = memu.MemuAdapter(fresh=True)
    info = m._bridge().info
    print(f"bridge up in {time.time() - t0:.0f}s: memU {info.get('memu_version')}, executor {info.get('executor')}, "
          f"embeddings {info.get('embedding')}")
    ss = sessions()
    t0 = time.time()
    runs = m.memorize(ss)
    for r in runs:
        print(f"run: {r['sessions']} sessions, {r['jobs']} jobs, {r['s']}s, executor {r['executor'].get('steps')} steps "
              f"{r['executor'].get('tools')}; changed {r['changed']}")
    print(f"{len(ss)} sessions memorized in {time.time() - t0:.0f}s -> {memu.STORE}")
    files = [f for f in m.files() if (f.get("content") or "").strip()]
    print(f"{len(files)} recall files:", ", ".join(f"{f['track']}/{f['name']}" for f in files))
    print("usage:", json.dumps(m._call("usage")["usage"]))
    m._b.close()
    return 0 if files else 1


if __name__ == "__main__":
    raise SystemExit(main())
