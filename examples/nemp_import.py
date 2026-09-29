"""Put the synthetic memory (examples/synthetic.py) into a fresh Nemp project,
one /nemp:save per memory, run by Claude Code as a user would:

    NEMP_PLUGIN=.../Nemp-memory NEMP_PROJECT=/tmp/nemp-project python examples/nemp_import.py
    python -m adebench --adapter adebench.nemp:NempAdapter \
        --cases examples/synthetic_data/cases --history /tmp/nemp-run

The project is emptied and made a git repository (Nemp keeps project memory
there). Keys are what a user would type: the entity for a card, the fact's
key for a fact, alias-<name>, episode-<date>-<n>. The value is the text as
given; Nemp's save instructions tell the model to compress it, and what it
keeps is Nemp's business. Nemp has no event date: a memory carries the time
it was written.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adebench import nemp  # noqa: E402
from examples.synthetic import ALIASES, CARDS, EPISODES, FACTS  # noqa: E402


def main() -> int:
    if not nemp.PROJECT or not nemp.PLUGIN:
        print("set NEMP_PLUGIN and NEMP_PROJECT")
        return 2
    proj = Path(nemp.PROJECT)
    shutil.rmtree(proj, ignore_errors=True)
    proj.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=proj, check=True)
    n = nemp.NempAdapter()
    items = [(ent, text) for ent, text in CARDS.items()]
    items += [(nemp.slug(f["key"]), f["content"]) for f in FACTS]
    items += [(f"alias-{nemp.slug(a['alias'])}", f"'{a['alias'].replace('_', ' ')}' is another name for {a['canonical']}.")
              for a in ALIASES]
    items += [(f"episode-{e['created_at'][:10]}-{i}", f"{e['input_summary']}. Result: {e['output_summary']}")
              for i, e in enumerate(EPISODES)]
    kept = 0
    for i, (key, value) in enumerate(items, 1):
        t0 = time.time()
        try:
            ok = n.save(key, value)
        except nemp.NempError as e:
            ok = None
            print("   ", str(e)[:120])
        kept += bool(ok)
        print(f"{i:2}/{len(items)} ({time.time() - t0:.0f}s) {'ok ' if ok else 'NO '} {key}")
    print(f"{kept} of {len(items)} saved in {proj}; {n.calls} model turns, ${n.cost_usd:.2f} at API prices")
    return 0 if kept else 1


if __name__ == "__main__":
    raise SystemExit(main())
