"""Put the synthetic memory (examples/synthetic.py) into TokenMizer the only
way TokenMizer learns anything: as a conversation through its proxy.

    tokenmizer serve --config tokenmizer.yaml     # use_llm_extraction: true, a real model behind it
    TOKENMIZER_URL=http://127.0.0.1:8020 python examples/tokenmizer_import.py

Each card, each fact and each episode is said once, in its own turn, as an
assistant would hear it from its user; the upstream model acknowledges, and
TokenMizer's extractor decides what of it becomes a node. Nothing is
rewritten, nothing is stored behind the proxy's back. A checkpoint at the end
makes the resume block that the `resume` door serves.

The session is `TOKENMIZER_SESSION` (default `adebench`), a scratch one.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adebench.tokenmizer import TokenmizerAdapter  # noqa: E402
from examples.synthetic import ALIASES, CARD_DATES, CARDS, EPISODES, FACTS  # noqa: E402


def main() -> int:
    t = TokenmizerAdapter()
    if not t.health():
        print(f"TokenMizer does not answer at {t.url}: start `tokenmizer serve` first")
        return 2
    turns = []
    for entity, text in CARDS.items():
        turns.append(f"About {entity.replace('_', ' ')} (as of {CARD_DATES[entity]}): {text}")
    for f in FACTS:
        turns.append(f"On {f['event_date']}: {f['content']}")
    for a in ALIASES:
        turns.append(f"When I say '{a['alias'].replace('_', ' ')}' I mean {a['canonical']}.")
    for e in EPISODES:
        turns.append(f"On {e['created_at'][:10]} I asked: {e['input_summary']}. Result: {e['output_summary']}")
    for i, text in enumerate(turns, 1):
        t0 = time.time()
        r = t.chat(text)
        reply = ((r.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        print(f"{i:2}/{len(turns)} ({time.time() - t0:.0f}s) {text[:60]!r} -> {str(reply)[:50]!r}")
    t.settle()
    ck = t.checkpoint()
    counts = t.graph_counts()
    print(f"session {t.session}: {counts.get('nodes')} nodes, {counts.get('edges')} edges, "
          f"checkpoint {ck.get('checkpoint_id')} ({ck.get('resume_tokens')} resume tokens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
